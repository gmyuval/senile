# -*- coding: utf-8 -*-

import pdb
import datetime
import json
import requests
from copy import deepcopy
from contextlib import contextmanager

BASE_REQUEST_PARTS = set(('CompanyParams', 'CompanyPermissions', 'CompanyPreferences', 'CompanyPreferencesPermissions'))
HEBREW = '3'
COMPANY_ID = '51267213'
BASE_URL = 'https://harmony.synel.co.il/eharmonynew/api/'
LOGIN_URL = BASE_URL + 'login/Login'
CHECK_URL = BASE_URL + 'Common/CheckUserLogin'
COMPANY_URL = BASE_URL + 'login/ConnectToCompanyFromPortal'
LOGOUT_URL = BASE_URL + 'login/RemoveSessionBySessionId'
GET_ATTENDANCE_URL = BASE_URL + 'Attendance/GetAttendance'
DELETE_ATTENDANCE = BASE_URL + 'Attendance/DeleteAttendanceFromGrid'
SAVE_ATTENDANCE_URL = BASE_URL + '/Attendance/SaveAttendanceFromGrid'
SKIP_TYPES = [s.decode('UTF-8') for s in ['שישי', 'שבת', 'חג']]
ATTENDANCE_TYPES = {'VACATION': 1, 'SICKDAY': 2, 'WORKDAY': 0, 'HALFDAY': 3}




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
        login_request['Password'] = password
        login_request['EmpIdOrName'] = username
        response = requests.post(LOGIN_URL, json=login_request)
        response.raise_for_status()
        cookies = response.cookies.get_dict()
        session_id = json.loads(response.content)['SessionId']

        yield (session_id, cookies)
        requests.post(LOGOUT_URL, json={'SessionId': session_id}, cookies=cookies)

    def check_login(self, username, password):
        with self.user_context(username, password) as (session_id, cookies):
            response = requests.post(CHECK_URL, headers={'sessionId': session_id}, cookies=cookies)
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
        query = {'xFromDate': today, 'xToDate': tomorrow, 'Emp_No': username,
                 'GroupCode': username, 'PageLength': '10', 'LPres': 1, 'Updatestatus': -1, 'GridType': 0,
                 'PageNo': 1}
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
        pdb.set_trace()
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

    def absence_report(self, username, password, absence_code, year=None):
        report = []
        if year is not None:
            year = datetime.datetime.strftime(year, '%Y')
        else:
            year = datetime.datetime.now().strftime('%Y')
        from_year = '{}-01-01T00:00:00'.format(year)
        to_year = '{}-01-01T00:00:00'.format(int(year) + 1)
        query = {'xFromDate': from_year, 'xToDate': to_year, 'Emp_No': username,
                 'FilterState': 'AbsenceCodeAW=\'{}\''.format(absence_code),
                 'GroupCode': username, 'PageLength': '31', 'LPres': 1, 'Updatestatus': -1, 'GridType': 0,
                 'PageNo': 1}
        url = '{}?query={}'.format(GET_ATTENDANCE_URL, requests.utils.quote(json.dumps(query)))
        with self.user_context(username, password) as (session_id, cookies):
            response = requests.get(url, headers={'sessionId': session_id}, cookies=cookies)
            response.raise_for_status()
            parsed = json.loads(response.content)
            if 'results' in parsed:
                for absence in parsed['results']:
                    report.append((absence['WorkDateA'].split('T')[0], absence['AbsenceTimeAW'], absence['Type']))
            else:
                report.append({parsed['WorkDateA'].split('T')[0]: (parsed['AbsenceTimeAW'], parsed['Type'])})
            return report


def main():
    connection = Synel(COMPANY_ID)
    import base64
    # print connection.get_attendance('--', '----')
    print connection.is_missing_clock_in_today('47', base64.b64encode('1234'))
    # print connection.report_attendance('--', '----', ATTENDANCE_TYPES['WORKDAY'], '2018-01-03')
    # print connection.get_attendance('--', '----')
    # print connection.absence_report('--', base64.b64encode('----'), ATTENDANCE_TYPES['VACATION'], year='2017')

if __name__ == '__main__':
    main()
