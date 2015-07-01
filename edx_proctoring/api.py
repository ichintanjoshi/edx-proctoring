# pylint: disable=unused-argument

# remove pylint rule after we implement each method

"""
In-Proc API (aka Library) for the edx_proctoring subsystem. This is not to be confused with a HTTP REST
API which is in the views.py file, per edX coding standards
"""
import pytz
from datetime import datetime, timedelta
from django.template import Context, loader
from django.core.urlresolvers import reverse

from edx_proctoring.exceptions import (
    ProctoredExamAlreadyExists, ProctoredExamNotFoundException, StudentExamAttemptAlreadyExistsException,
    StudentExamAttemptDoesNotExistsException)
from edx_proctoring.models import (
    ProctoredExam, ProctoredExamStudentAllowance, ProctoredExamStudentAttempt
)
from edx_proctoring.serializers import ProctoredExamSerializer, ProctoredExamStudentAttemptSerializer, \
    ProctoredExamStudentAllowanceSerializer
from edx_proctoring.utils import humanized_time


def create_exam(course_id, content_id, exam_name, time_limit_mins,
                is_proctored=True, external_id=None, is_active=True):
    """
    Creates a new ProctoredExam entity, if the course_id/content_id pair do not already exist.
    If that pair already exists, then raise exception.

    Returns: id (PK)
    """
    if ProctoredExam.get_exam_by_content_id(course_id, content_id) is not None:
        raise ProctoredExamAlreadyExists

    proctored_exam = ProctoredExam.objects.create(
        course_id=course_id,
        content_id=content_id,
        external_id=external_id,
        exam_name=exam_name,
        time_limit_mins=time_limit_mins,
        is_proctored=is_proctored,
        is_active=is_active
    )
    return proctored_exam.id


def update_exam(exam_id, exam_name=None, time_limit_mins=None,
                is_proctored=None, external_id=None, is_active=None):
    """
    Given a Django ORM id, update the existing record, otherwise raise exception if not found.
    If an argument is not passed in, then do not change it's current value.

    Returns: id
    """
    proctored_exam = ProctoredExam.get_exam_by_id(exam_id)
    if proctored_exam is None:
        raise ProctoredExamNotFoundException

    if exam_name is not None:
        proctored_exam.exam_name = exam_name
    if time_limit_mins is not None:
        proctored_exam.time_limit_mins = time_limit_mins
    if is_proctored is not None:
        proctored_exam.is_proctored = is_proctored
    if external_id is not None:
        proctored_exam.external_id = external_id
    if is_active is not None:
        proctored_exam.is_active = is_active
    proctored_exam.save()
    return proctored_exam.id


def get_exam_by_id(exam_id):
    """
    Looks up exam by the Primary Key. Raises exception if not found.

    Returns dictionary version of the Django ORM object
    e.g.
    {
        "course_id": "edX/DemoX/Demo_Course",
        "content_id": "123",
        "external_id": "",
        "exam_name": "Midterm",
        "time_limit_mins": 90,
        "is_proctored": true,
        "is_active": true
    }
    """
    proctored_exam = ProctoredExam.get_exam_by_id(exam_id)
    if proctored_exam is None:
        raise ProctoredExamNotFoundException

    serialized_exam_object = ProctoredExamSerializer(proctored_exam)
    return serialized_exam_object.data


def get_exam_by_content_id(course_id, content_id):
    """
    Looks up exam by the course_id/content_id pair. Raises exception if not found.

    Returns dictionary version of the Django ORM object
    e.g.
    {
        "course_id": "edX/DemoX/Demo_Course",
        "content_id": "123",
        "external_id": "",
        "exam_name": "Midterm",
        "time_limit_mins": 90,
        "is_proctored": true,
        "is_active": true
    }
    """
    proctored_exam = ProctoredExam.get_exam_by_content_id(course_id, content_id)
    if proctored_exam is None:
        raise ProctoredExamNotFoundException

    serialized_exam_object = ProctoredExamSerializer(proctored_exam)
    return serialized_exam_object.data


def add_allowance_for_user(exam_id, user_id, key, value):
    """
    Adds (or updates) an allowance for a user within a given exam
    """
    ProctoredExamStudentAllowance.add_allowance_for_user(exam_id, user_id, key, value)


def remove_allowance_for_user(exam_id, user_id, key):
    """
    Deletes an allowance for a user within a given exam.
    """
    student_allowance = ProctoredExamStudentAllowance.get_allowance_for_user(exam_id, user_id, key)
    if student_allowance is not None:
        student_allowance.delete()


def get_exam_attempt(exam_id, user_id):
    """
    Return an existing exam attempt for the given student
    """
    exam_attempt_obj = ProctoredExamStudentAttempt.get_student_exam_attempt(exam_id, user_id)
    return exam_attempt_obj.__dict__ if exam_attempt_obj else None


def start_exam_attempt(exam_id, user_id, external_id):
    """
    Signals the beginning of an exam attempt for a given
    exam_id. If one already exists, then an exception should be thrown.

    Returns: exam_attempt_id (PK)
    """
    exam_attempt_obj = ProctoredExamStudentAttempt.start_exam_attempt(exam_id, user_id, external_id)
    if exam_attempt_obj is None:
        raise StudentExamAttemptAlreadyExistsException
    else:
        return exam_attempt_obj.id


def stop_exam_attempt(exam_id, user_id):
    """
    Marks the exam attempt as completed (sets the completed_at field and updates the record)
    """
    exam_attempt_obj = ProctoredExamStudentAttempt.get_student_exam_attempt(exam_id, user_id)
    if exam_attempt_obj is None:
        raise StudentExamAttemptDoesNotExistsException
    else:
        exam_attempt_obj.completed_at = datetime.now(pytz.UTC)
        exam_attempt_obj.save()
        return exam_attempt_obj.id


def get_active_exams_for_user(user_id, course_id=None):
    """
    This method will return a list of active exams for the user,
    i.e. started_at != None and completed_at == None. Theoretically there
    could be more than one, but in practice it will be one active exam.

    If course_id is set, then attempts only for an exam in that course_id
    should be returned.

    The return set should be a list of dictionary objects which are nested


    [{
        'exam': <exam fields as dict>,
        'attempt': <student attempt fields as dict>,
        'allowances': <student allowances as dict of key/value pairs
    }, {}, ...]

    """
    result = []

    student_active_exams = ProctoredExamStudentAttempt.get_active_student_exams(user_id, course_id)
    for active_exam in student_active_exams:
        # convert the django orm objects
        # into the serialized form.
        exam_serialized_data = ProctoredExamSerializer(active_exam.proctored_exam).data
        active_exam_serialized_data = ProctoredExamStudentAttemptSerializer(active_exam).data
        student_allowances = ProctoredExamStudentAllowance.get_allowances_for_user(
            active_exam.proctored_exam.id, user_id
        )
        allowance_serialized_data = [ProctoredExamStudentAllowanceSerializer(allowance).data for allowance in
                                     student_allowances]
        result.append({
            'exam': exam_serialized_data,
            'attempt': active_exam_serialized_data,
            'allowances': allowance_serialized_data
        })

    return result


def get_student_view(user_id, course_id, content_id, context):
    """
    Helper method that will return the view HTML related to the exam control
    flow (i.e. entering, expired, completed, etc.) If there is no specific
    content to display, then None will be returned and the caller should
    render it's own view
    """

    has_started_exam = False
    has_finished_exam = False
    has_time_expired = False
    is_proctored = False
    student_view_template = None

    exam_id = None
    try:
        exam = get_exam_by_content_id(course_id, content_id)
        exam_id = exam['id']
        is_proctored = exam['is_proctored']
    except ProctoredExamNotFoundException:
        is_proctored = context.get('is_proctored', False)
        exam_id = create_exam(
            course_id=course_id,
            content_id=unicode(content_id),
            exam_name=context['display_name'],
            time_limit_mins=context['default_time_limit_mins'],
            is_proctored=is_proctored
        )

    attempt = get_exam_attempt(exam_id, user_id)
    has_started_exam = attempt is not None
    if attempt:
        now_utc = datetime.now(pytz.UTC)
        expires_at = attempt['started_at'] + timedelta(minutes=context['default_time_limit_mins'])
        has_time_expired = now_utc > expires_at

    if not has_started_exam:
        # determine whether to show a timed exam only entrace screen
        # or a screen regarding proctoring
        if is_proctored:
            student_view_template = 'proctoring/seq_proctored_exam_entrance.html'
        else:
            student_view_template = 'proctoring/seq_timed_exam_entrance.html'
    elif has_finished_exam:
        student_view_template = 'proctoring/seq_timed_exam_completed.html'
    elif has_time_expired:
        student_view_template = 'proctoring/seq_timed_exam_expired.html'

    if student_view_template:
        template = loader.get_template(student_view_template)
        django_context = Context(context)
        total_time = humanized_time(context['default_time_limit_mins'])
        django_context.update({
            'total_time': total_time,
            'exam_id': exam_id,
            'enter_exam_endpoint': reverse('edx_proctoring.proctored_exam.attempt'),
        })
        return template.render(django_context)

    return None