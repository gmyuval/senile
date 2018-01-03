# -*- coding: utf-8 -*-

import pdb
import base64
import datetime
import json
import requests
from copy import deepcopy
from contextlib import contextmanager

# SAVE_DEFAULTS = {'NumeratorA': '', 'check_row': '', 'ExceptType': '', 'Emp_Name': '', 'Emp_noA': '', 'ApproveDateA': '',
#                  'WorkDateA': '', 'DateA': '', 'DayName': '', 'shift1_start': '', 'shift1_end': '', 'shift2_start': '',
#                  'shift2_end': '', 'Type': '', 'Schedular': '', 'Time_startA_RND': '', 'Time_endA_RND': '',
#                  'UpdateStatCodeAW': '', 'ExpectedTimeAW': '', 'intHand': '', 'budgID_AW': '', 'budgDescr_AW': '',
#                  'subBudgDescr_AW': '', 'subBudgID_AW': '', 'OperAW': '', 'OperNameAW': '', 'ActionAW': '',
#                  'ActionNameAW': '', 'Code_startAW': '', 'NameTrnFnc_startAW': '', 'Code_endAW': 0,
#                  'NameTrnFnc_endAW': '', 'OT_ApprTypeNameAW': '', 'OT_ApprTypeAW': '', 'NameAbsenceCodeAW': '',
#                  'AbsenceCodeAW': '', 'LPresentA': '', 'UserCommentAW': '', 'IsNonWorkDay': '', 'Exception': ''}
# SAVE_FIELDS = {'check_row': {'editable': False}, 'ExceptType': {'editable': False}, 'Emp_Name': {'editable': False},
#                'Emp_noA': {'editable': False}, 'ApproveDateA': {'editable': False, 'type': 'string'},
#                'WorkDateA': {'editable': False, 'type': 'string'}, 'DateA': {'editable': False, 'type': 'string'},
#                'DayName': {'editable': False}, 'shift1_start': {'editable': False}, 'shift1_end': {'editable': False},
#                'shift2_start': {'editable': False}, 'shift2_end': {'editable': False}, 'Type': {'editable': False},
#                'Schedular': {'editable': False}, 'Time_startA_RND': {'editable': False},
#                'Time_endA_RND': {'editable': False},'UpdateStatCodeAW': {'editable': False},
#                'ExpectedTimeAW': {'editable': False}, 'intHand': {'editable': False}, 'budgID_AW': {'editable': True},
#                'budgDescr_AW': {'editable': True, 'validation': {}},'subBudgDescr_AW': {'editable': True},
#                'subBudgID_AW': {'editable': True}, 'OperAW': {'editable': True}, 'OperNameAW': {'editable': True},
#                'ActionAW': {'editable': True}, 'ActionNameAW': {'editable': True}, 'Code_startAW': {'editable': True},
#                'NameTrnFnc_startAW': {'editable': True}, 'Code_endAW': {'editable': True, 'type': 'number'},
#                'NameTrnFnc_endAW': {'editable': True}, 'Time_startAW': {'type': 'time', 'editable': True},
#                'Time_endAW': {'type': 'time', 'editable': True}, 'AbsenceTimeAW': {'type': 'time', 'editable': True},
#                'OT_TimeAW': {'type': 'time', 'editable': True}, 'OT_ApprTypeNameAW': {'editable': False},
#                'OT_ApprTypeAW': {'editable': True}, 'NameAbsenceCodeAW': {'editable': True},
#                'AbsenceCodeAW': {'editable': True}, 'LPresentA': {'editable': False},
#                'UserCommentAW': {'editable': True, 'validation': {'maxlength': 100}},
#                'IsNonWorkDay': {'editable': False}, 'Exception': {'editable': False}}
BASE_REQUEST_PARTS = set(('CompanyParams', 'CompanyPermissions', 'CompanyPreferences', 'CompanyPreferencesPermissions'))
HEBREW = '3'
COMPANY_ID = ''
BASE_URL = 'https://harmony.synel.co.il/eharmonynew/api/'
LOGIN_URL = BASE_URL + 'login/Login'
CHECK_URL = BASE_URL + 'Common/CheckUserLogin'
COMPANY_URL = BASE_URL + 'login/ConnectToCompanyFromPortal'
LOGOUT_URL = BASE_URL + 'login/RemoveSessionBySessionId'
GET_ATTENDANCE_URL = BASE_URL + 'Attendance/GetAttendance'
DELETE_ATTENDANCE = BASE_URL + 'Attendance/DeleteAttendanceFromGrid'
SAVE_ATTENDANCE_URL = BASE_URL + '/Attendance/SaveAttendanceFromGrid'
SKIP_TYPES = [s.decode('UTF-8') for s in ['שישי', 'שבת', 'חג']]
ATTENDANCE_TYPES = {'VACATION': 0, 'SICKDAY': 1, 'WORKDAY': 2, 'HALFDAY': 3}



class Synel():
    def __init__(self, company_id):
        self.cookie = None
        self.cookies = {}
        company_details = {'CompanyId': company_id, 'languageId': HEBREW, 'CheckComp': True}
        response = requests.post(COMPANY_URL, json=company_details)
        response.raise_for_status()
        self.base_login_request = {k: v for k, v in json.loads(response.content).iteritems() if k in BASE_REQUEST_PARTS}
        self.base_login_request['CompanyId'] = company_id
        self.base_login_request['IsId'] = True
        self.base_login_request['languageId'] = HEBREW

    @contextmanager
    def user_context(self, username, password):
        login_request = deepcopy(self.base_login_request)
        login_request['Password'] = base64.b64encode(password)
        login_request['EmpIdOrName'] = username
        response = requests.post(LOGIN_URL, json=login_request)
        response.raise_for_status()
        cookies = response.cookies.get_dict()
        session_id = json.loads(response.content)['SessionId']

        yield (session_id, cookies)
        requests.post(LOGOUT_URL, json={'SessionId': session_id}, cookies=cookies)

    def check_login(self, username, password):
        with self.user_context(username, password) as (session_id, cookies):
            response = requests.post(CHECK_URL, headers={'sessionId': session_id}, cookies=cookies).content
            response.raise_for_status()
            return response.content == 'true'

    @staticmethod
    def _get_one_day_range(today=None):
        if today is not None:
            day = datetime.datetime.strptime(today, '%Y-%m-%d')
            today = '{}T00:00:00'.format(today)
            tomorrow = '{}T00:00:00'.format((day + datetime.timedelta(days=1)).strftime('%Y-%m-%d'))
        else:
            today = '{}T00:00:00'.format(datetime.datetime.now().strftime('%Y-%m-%d'))
            tomorrow = '{}T00:00:00'.format((datetime.date.today() + datetime.timedelta(days=1)).strftime('%Y-%m-%d'))
        return today, tomorrow

    def get_attendance(self, username, password, today=None):
        today, tomorrow = Synel._get_one_day_range(today)
        query = {'xFromDate': today, 'xToDate': tomorrow, 'Emp_No': 47,
                 'GroupCode': 47, 'PageLength': '10', 'LPres': 1, 'Updatestatus': -1, 'GridType': 0, 'PageNo': 1, }
        url = '{}?query={}'.format(GET_ATTENDANCE_URL, requests.utils.quote(json.dumps(query)))
        with self.user_context(username, password) as (session_id, cookies):
            response = requests.get(url, headers={'sessionId': session_id}, cookies=cookies)
            response.raise_for_status()
            print response.content
            parsed = json.loads(response.content)
            if 'results' in parsed:
                result = [r for r in parsed['results'] if r['WorkDateA'] == today][0]
            else:
                result = parsed
            return result

    def is_missing_clock_in_today(self, username, password, today=None):
        attendance = self.get_attendance(username, password, today=today)
        if attendance['Time_startA'] == '' and attendance['Type'] not in SKIP_TYPES\
                and attendance['AbsenceCodeAW'] == '':
                return True
        return False

    def report_attendance(self, username, password, attendance_type, today=None):
        request = self._build_attendance_request(username, password, attendance_type, today)
        today, tomorrow = Synel._get_one_day_range(today)
        with self.user_context(username, password) as (session_id, cookies):
            response = requests.post(SAVE_ATTENDANCE_URL, headers={'sessionId': session_id}, cookies=cookies,
                                     json=request)
            response.raise_for_status()

    def _build_attendance_request(self, username, password, attendance_type, today=None):
        attendance_request = {'Emp_no': username, 'UserNo': 9999, 'IsGrid': True, 'IsGroupUpdate': False,
                              'AutoApprove': 1, 'AttendanceList': [], 'dirtyFields': {}, 'defaults': {},
                              'fields': {}, 'idField': 'NumeratorA', '_defaultId': ''}
        current_attendance = self.get_attendance(username, password, today)
        current_attendance['OT_ApprTypeAW'] = None
        if attendance_type == ATTENDANCE_TYPES['VACATION']:
            current_attendance['AbsenceCodeAW'] = '1'
            current_attendance['NameAbsenceCodeAW'] = 'חופשה'
            current_attendance['AbsenceTimeAW'] = '09:00'
            current_attendance['Code_startAW'] = None
            current_attendance['NameTrnFnc_startAW'] = None
            current_attendance['NameTrnFnc_endAW'] = None
            current_attendance['Code_endAW'] = None
            current_attendance['budgID_AW'] = ''
            current_attendance['budgDescr_AW'] = ''
            current_attendance.update({'Time_endA': '', 'Time_endA_RND': '', 'Time_endAW': '00:00:00',
                                       'Time_startA': '', 'Time_startA_RND': '', 'Time_startAW': '00:00:00'})
        elif attendance_type == ATTENDANCE_TYPES['SICKDAY']:
            current_attendance['AbsenceCodeAW'] = '2'
            current_attendance['NameAbsenceCodeAW'] = 'מחלת עובד'
            current_attendance['AbsenceTimeAW'] = '09:00'
            current_attendance['Code_startAW'] = None
            current_attendance['NameTrnFnc_startAW'] = None
            current_attendance['NameTrnFnc_endAW'] = None
            current_attendance['Code_endAW'] = None
            current_attendance['budgID_AW'] = ''
            current_attendance['budgDescr_AW'] = ''
            current_attendance.update({'Time_endA': '', 'Time_endA_RND': '', 'Time_endAW': '00:00:00',
                                       'Time_startA': '', 'Time_startA_RND': '', 'Time_startAW': '00:00:00'})
        elif attendance_type == ATTENDANCE_TYPES['WORKDAY']:
            current_attendance['AbsenceCodeAW'] = ''
            current_attendance['NameAbsenceCodeAW'] = ''
            current_attendance['AbsenceTimeAW'] = '00:00'
            current_attendance['Code_startAW'] = '500'
            current_attendance['NameTrnFnc_startAW'] = 'כניסה+פרוייקט'
            current_attendance['NameTrnFnc_endAW'] = 'יציאה'
            current_attendance['Code_endAW'] = '200'
            current_attendance['budgID_AW'] = '57183'
            current_attendance['budgDescr_AW'] = 'מדען'
            current_attendance.update({'Time_endA': '', 'Time_endA_RND': '', 'Time_endAW': '18:00:00',
                                       'Time_startA': '', 'Time_startA_RND': '', 'Time_startAW': '09:00:58'})
        elif attendance_type == ATTENDANCE_TYPES['HALFDAY']:
            current_attendance['AbsenceCodeAW'] = '1'
            current_attendance['NameAbsenceCodeAW'] = 'חופשה'
            current_attendance['AbsenceTimeAW'] = '04:30'
            current_attendance['Code_startAW'] = '500'
            current_attendance['NameTrnFnc_startAW'] = 'כניסה+פרוייקט'
            current_attendance['NameTrnFnc_endAW'] = 'יציאה'
            current_attendance['Code_endAW'] = '200'
            current_attendance['budgID_AW'] = '57183'
            current_attendance['budgDescr_AW'] = 'מדען'
            current_attendance.update({'Time_endA': '', 'Time_endA_RND': '', 'Time_endAW': '13:30:00',
                                       'Time_startA': '', 'Time_startA_RND': '', 'Time_startAW': '09:00:58'})
        else:
            raise AttributeError('Unknown attendance type')
        attendance_request['dirtyFields'].update({'AbsenceCodeAW': True, 'NameAbsenceCodeAW': True,
                                                  'AbsenceTimeAW': True, 'Time_endA': True, 'Time_endA_RND': True,
                                                  'Time_endAW': True, 'Time_startA': True, 'Time_startA_RND': True,
                                                  'Time_startAW': True, 'Code_startAW': True,
                                                  'NameTrnFnc_startAW': True, 'NameTrnFnc_endAW': True,
                                                  'Code_endAW': True, 'budgID_AW': True, 'budgDescr_AW': True})
        attendance_request['AttendanceList'].append(current_attendance)
        return attendance_request


def main():
    connection = Synel(COMPANY_ID)
    # print connection.get_attendance('--', '----')
    # print connection.is_missing_clock_in_today('--', '----', '2017-12-30')
    print connection.report_attendance('--', '----', ATTENDANCE_TYPES['WORKDAY'])


if __name__ == '__main__':
    main()
