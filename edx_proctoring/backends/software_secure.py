"""
Integration with Software Secure's proctoring system
"""

from Crypto.Cipher import DES3
import base64
from hashlib import sha256
import requests
import hmac
import binascii
import datetime
import json
import logging

from edx_proctoring.backends.backend import ProctoringBackendProvider
from edx_proctoring.exceptions import BackendProvideCannotRegisterAttempt


log = logging.getLogger(__name__)


class SoftwareSecureBackendProvider(ProctoringBackendProvider):
    """
    Implementation of the ProctoringBackendProvider for Software Secure's
    RPNow product
    """

    def __init__(self, organization, exam_sponsor, exam_register_endpoint,
                 secret_key_id, secret_key, crypto_key, software_download_url):
        """
        Class initializer
        """

        self.organization = organization
        self.exam_sponsor = exam_sponsor
        self.exam_register_endpoint = exam_register_endpoint
        self.secret_key_id = secret_key_id
        self.secret_key = secret_key
        self.crypto_key = crypto_key
        self.timeout = 10
        self.software_download_url = software_download_url

    def register_exam_attempt(self, exam, time_limit_mins, attempt_code,
                              is_sample_attempt, callback_url):
        """
        Method that is responsible for communicating with the backend provider
        to establish a new proctored exam
        """

        data = self._get_payload(
            exam,
            time_limit_mins,
            attempt_code,
            is_sample_attempt,
            callback_url
        )
        headers = {
            "Content-Type": 'application/json'
        }
        http_date = datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
        signature = self._sign_doc(data, 'POST', headers, http_date)

        status, response = self._send_request_to_ssi(data, signature, http_date)

        if status not in [200, 201]:
            err_msg = (
                'Could not register attempt_code = {attempt_code}. '
                'HTTP Status code was {status_code} and response was {response}.'.format(
                    attempt_code=attempt_code,
                    status_code=status,
                    response=response
                )
            )
            raise BackendProvideCannotRegisterAttempt(err_msg)

        # get the external ID that Software Secure has defined
        # for this attempt
        ssi_record_locator = json.loads(response)['ssiRecordLocator']

        return ssi_record_locator

    def start_exam_attempt(self, exam, attempt):  # pylint: disable=unused-argument
        """
        Called when the exam attempt has been created but not started
        """
        return None

    def stop_exam_attempt(self, exam, attempt):
        """
        Method that is responsible for communicating with the backend provider
        to establish a new proctored exam
        """
        return None

    def get_software_download_url(self):
        """
        Returns the URL that the user needs to go to in order to download
        the corresponding desktop software
        """
        return self.software_download_url

    def _encrypt_password(self, key, pwd):
        """
        Encrypt the exam passwork with the given key
        """
        block_size = DES3.block_size

        def pad(text):
            """
            Apply padding
            """
            return text + (block_size - len(text) % block_size) * chr(block_size - len(text) % block_size)
        cipher = DES3.new(key, DES3.MODE_ECB)
        encrypted_text = cipher.encrypt(pad(pwd))
        return base64.b64encode(encrypted_text)

    def _get_payload(self, exam, time_limit_mins, attempt_code,
                     is_sample_attempt, callback_url):
        """
        Constructs the data payload that Software Secure expects
        """
        now = datetime.datetime.utcnow()
        start_time_str = now.strftime("%a, %d %b %Y %H:%M:%S GMT")
        end_time_str = (now + datetime.timedelta(minutes=time_limit_mins)).strftime("%a, %d %b %Y %H:%M:%S GMT")
        return {
            "examCode": attempt_code,
            "organization": self.organization,
            "duration": time_limit_mins,
            "reviewedExam": not is_sample_attempt,
            "reviewerNotes": 'Closed Book',
            "examPassword": self._encrypt_password(self.crypto_key, attempt_code),
            "examSponsor": self.exam_sponsor,
            "examName": exam['exam_name'],
            "ssiProduct": 'rp-now',
            # need to pass in a URL to the LMS?
            "examUrl": callback_url,
            "orgExtra": {
                "examStartDate": start_time_str,
                "examEndDate": end_time_str,
                "noOfStudents": 1,
                "examID": exam['id'],
                "courseID": exam['course_id'],
            }
        }

    def _header_string(self, headers, date):
        """
        Composes the HTTP header string that SoftwareSecure expects
        """
        # Headers
        string = ""
        if 'Content-Type' in headers:
            string += headers.get('Content-Type')
            string += '\n'

        if date:
            string += date
            string += '\n'

        return string

    def _body_string(self, body_json, prefix=""):
        """
        Serializes out the HTTP body that SoftwareSecure expects
        """
        keys = body_json.keys()
        keys.sort()
        string = ""
        for key in keys:
            value = body_json[key]
            if str(value) == 'True':
                value = 'true'
            if str(value) == 'False':
                value = 'false'
            if isinstance(value, (list, tuple)):
                for idx, arr in enumerate(value):
                    if isinstance(arr, dict):
                        string += self._body_string(arr, key + '.' + str(idx) + '.')
                    else:
                        string += key + '.' + str(idx) + ':' + arr + '\n'
            elif isinstance(value, dict):
                string += self._body_string(value, key + '.')
            else:
                if value != "" and not value:
                    value = "null"
                string += str(prefix) + str(key) + ":" + str(value).encode('utf-8') + '\n'

        return string

    def _sign_doc(self, body_json, method, headers, date):
        """
        Digitaly signs the datapayload that SoftwareSecure expects
        """
        body_str = self._body_string(body_json)

        method_string = method + '\n\n'

        headers_str = self._header_string(headers, date)
        message = method_string + headers_str + body_str

        # HMAC requires a string not a unicode
        message = str(message)

        log_msg = (
            'About to send payload to SoftwareSecure:\n{message}'.format(message=message)
        )
        log.info(log_msg)

        hashed = hmac.new(str(self.secret_key), str(message), sha256)
        computed = binascii.b2a_base64(hashed.digest()).rstrip('\n')

        return 'SSI ' + self.secret_key_id + ':' + computed

    def _send_request_to_ssi(self, data, sig, date):
        """
        Performs the webservice call to SoftwareSecure
        """
        response = requests.post(
            self.exam_register_endpoint,
            headers={
                'Content-Type': 'application/json',
                "Authorization": sig,
                "Date": date
            },
            data=json.dumps(data),
            timeout=self.timeout
        )

        return response.status_code, response.text