import os
import time
import re
import pdb
import base64
from gevent import Greenlet
from slackclient import SlackClient
import requests
import boto3
import json
from botocore.exceptions import ClientError
from synel import Synel, ATTENDANCE_TYPES

ACTION_MSG1 = {
    "text": "Eh, forgot to clock-in today?",
    "attachments": [
        {
            "fallback": "You are unable to choose a game",
            "callback_id": "senile_action",
            "color": "#3AA3E3",
            "attachment_type": "default",
            "actions": [
                {
                    "name": "action",
                    "text": "I'm here",
                    "type": "button",
                    "value": "full_day"
                },
                {
                    "name": "action",
                    "text": "Half day off",
                    "type": "button",
                    "value": "half_day"
                },
                {
                    "name": "action",
                    "text": "Not here",
                    "type": "button",
                    "value": "day_off"
                },
                {
                    "name": "action",
                    "text": "Sick day",
                    "type": "button",
                    "value": "sick_day"
                }
            ]
        }
    ]
}

ERROR_MSG1 = 'No good, to register try: register <synel_user_id> <synel_password> <manager_slack_user>'
ERROR_MSG2 = 'Are you senile? could not register to synel using the given username and password'



class SenileBot(object):
    RTM_READ_DELAY = 1  # 1 second delay between reading from RTM
    MENTION_REGEX = "^<@(|[WU].+)>(.*)"
    USERS_URL = 'https://slack.com/api/users.list'
    NGINX_IP = '192.168.206.41'
    NGINX_PORT = '8081'
    MGMT_IP = '192.168.202.16'
    MGMT_PORT = '8001'
    USERS_TABLE = 'registered_users'

    def __init__(self):
        self.app_token = os.environ.get('SLACK_BOT_TOKEN')
        self.slack_client = SlackClient(self.app_token)
        self.slack_users = self.slack_users_list()
        self.synel = Synel(os.environ.get('COMPANY_ID'))
        self.bot_id = None
        self.available_commands = {
            'register': self.register_user,
            'unregister': self.unregister_user,
            'notify': self.missing_clock_notification,
            'show_vacations': self.get_vacations,
            'show_sickdays': self.get_sickdays,
            'vacation': self.set_vacation,
            'sickday': self.set_sickday,
            'workday': self.set_workday,
            'halfday': self.set_halfday,
        }  # type: dict[(), ()]
        self.connect()

        self.dyndb = boto3.client('dynamodb', endpoint_url='http://{}:{}'.format(self.NGINX_IP, self.NGINX_PORT),
                                  iguazio_management_url='http://{}:{}'.format(self.MGMT_IP, self.MGMT_PORT),
                                  is_iguazio_api=True, iguazio_management_username='iguazio',
                                  iguazio_management_password='Password1', region_name='lala')

        response = requests.get('http://{}:{}/{}?prefix=/{}/'.format(self.NGINX_IP, self.NGINX_PORT, '1',
                                                                     self.USERS_TABLE))
        if response.status_code >= '400':
            self.dyndb.create_table(TableName=self.USERS_TABLE,
                                    Bucket='1',
                                    KeySchema=[{'AttributeName': 'slack_user', 'KeyType': 'HASH'}])
        if not self.bot_id:
            raise RuntimeError('Failed connecting to slack.')

    def slack_users_list(self):
        response = requests.get('{}?token='.format(self.USERS_URL, self.app_token))
        response.raise_for_status()
        return response.content

    def get_slack_profile_detail(self, user_id, detail_name):
        user = [u for u in self.slack_users['members'] if u.id == user_id].pop()
        return user[detail_name]

    def connect(self):
        if self.slack_client.rtm_connect():
            print("Senile Bot connected and running!")
            # Read bot's user ID by calling Web API method `auth.test`
            self.bot_id = self.slack_client.api_call("auth.test")["user_id"]
        else:
            print("Connection failed. Exception traceback printed above.")

    def run_loop(self):
        while True:
            events = self.slack_client.rtm_read()
            for event in events:
                print(event)
            command, channel, user = self.parse_bot_commands(events)
            if command:
                self.handle_command(command, channel, user)
            time.sleep(self.RTM_READ_DELAY)

    def parse_bot_commands(self, slack_events):
        """
            Parses a list of events coming from the Slack RTM API to find bot commands.
            If a bot command is found, this function returns a tuple of command and channel.
            If its not found, then this function returns None, None.
        """
        for event in slack_events:
            if event["type"] == "message" and not "subtype" in event:
                direct_mention = re.search(self.MENTION_REGEX, event['text'])
                if direct_mention and direct_mention.group(1) == self.bot_id:
                    return direct_mention.group(2).strip(), event['channel'], event['user']
                elif self.slack_client.api_call('conversations.info', channel=event['channel'])['channel']['is_im']:
                    return event['text'], event['channel'], event['user']
        return None, None, None

    def handle_command(self, command_text, channel, user_id):
        """
            Executes bot command if the command is known
        """
        # Default response is help text for the user
        default_response = "Not sure what you mean. Try one of the existing commands:\n{}"\
            .format('\n'.join(self.available_commands.iterkeys()))

        # Finds and executes the given command, filling in response
        response = None
        # This is where you start to implement more commands!
        command = command_text.split()[0]
        if command.lower() in self.available_commands:
            response = self.available_commands[command.lower()](user_id, ' '.join(command_text.split()[1:]))

        # Sends the response back to the channel
        self.slack_client.api_call(
            "chat.postMessage",
            channel=channel,
            text=response or default_response
        )

    def register_user(self, user_id, command_text):
        match = re.search(r'(\d+)\s+(\S+)$', command_text)
        if not match:
            return ERROR_MSG1
        synel_user = match.group(1)
        synel_pass = base64.b64encode(match.group(2))
        try:
            self.synel.check_login(synel_user, synel_pass)
        except Exception as e:
            return ERROR_MSG2
        self.dyndb.put_item(TableName=self.USERS_TABLE, Bucket='1', validate_exists=False,
                            Item=dict(slack_user=dict(S=user_id),
                                      synel_user=dict(S=synel_user),
                                      synel_pass=dict(S=synel_pass)))
        return 'Registered user {} with password {}'.format(synel_user, synel_pass)

    def unregister_user(self, user_id, *args):
        try:
            self.dyndb.get_item(TableName=self.USERS_TABLE, Bucket='1',
                                AttributesToGet='slack_user', Key=dict(slack_user=dict(S=user_id)))
        except ClientError:
            return 'You are not register. Perhaps try \'register\' before?'
        try:
            self.dyndb.delete_item(TableName=self.USERS_TABLE, Bucket='1',
                                   Key=dict(slack_user=dict(S=user_id)))
        except ClientError:
            return 'Something went wrong. Maybe try again later.'

        return 'Congratulations, you\'ve removed yourself from senile'

    def missing_clock_notification(self, *args, **kwargs):
        entries = []
        res = self.dyndb.scan(TableName='{}/'.format(self.USERS_TABLE), Bucket='1',
                              AttributesToGet=['slack_user', 'synel_user', 'synel_pass'])
        entries.extend(res['Items'])
        while 'LastEvaluatedKey' in res:
            res = self.dyndb.scan(TableName='{}/'.format(self.USERS_TABLE), Bucket='1',
                                  AttributesToGet=['slack_user', 'synel_user', 'synel_pass'],
                                  ExclusiveStartKey=res['LastEvaluatedKey'])
            entries.extend(res['Items'])
        for entry in entries:
            inform = False
            try:
                inform = self.synel.is_missing_clock_in_today(entry['synel_user']['S'], entry['synel_pass']['S'])
            except:
                pass
            if inform:
                self.slack_client.api_call(
                    'chat.postMessage',
                    channel=entry['slack_user']['S'],
                    text=ACTION_MSG1['text'],
                )
        return 'Everyone was notified'

    def set_vacation(self, user_id, command_text):
        return self.set_attendance(user_id, command_text, ATTENDANCE_TYPES['VACATION'])

    def set_sickday(self, user_id, command_text):
        return self.set_attendance(user_id, command_text, ATTENDANCE_TYPES['SICKDAY'])

    def set_halfday(self, user_id, command_text):
        return self.set_attendance(user_id, command_text, ATTENDANCE_TYPES['HALFDAY'])

    def set_workday(self, user_id, command_text):
        return self.set_attendance(user_id, command_text, ATTENDANCE_TYPES['WORKDAY'])

    def set_attendance(self, user_id, command_text, attendance_type):
        if command_text:
            match = re.search(r'\d\d\d\d-\d\d-\d\d$', command_text)
            if not match:
                return 'Illegal date format. Please send date in format YYYY-mm-dd or no date at all for today.'
            date = match.group()
        else:
            date = None
        try:
            entry = self.dyndb.get_item(TableName=self.USERS_TABLE, Bucket='1',
                                        AttributesToGet='slack_user,synel_user,synel_pass', Key=dict(slack_user=dict(S=user_id)))
        except ClientError:
            return 'You are not register. Perhaps try \'register\' before?'
        try:
            self.synel.report_attendance(entry['Item']['synel_user']['S'], entry['Item']['synel_pass']['S'], attendance_type, today=date)
        except Exception:
            return 'Future is murky and thus unreportable'
        return 'You have reported your attendance'

    def get_vacations(self, user_id, command_text):
        return self.list_attendance(user_id, command_text, ATTENDANCE_TYPES['VACATION'])

    def get_sickdays(self, user_id, command_text):
        return self.list_attendance(user_id, command_text, ATTENDANCE_TYPES['SICKDAY'])

    def list_attendance(self, user_id, command_text, absense_code):
        if command_text:
            match = re.search(r'\d\d\d\d', command_text)
            if not match or match.group() not in ['2017', '2018']:
                return 'Illegal year'
            year = match.group()
        else:
            year = None
        try:
            entry = self.dyndb.get_item(TableName=self.USERS_TABLE, Bucket='1',
                                        AttributesToGet='slack_user,synel_user,synel_pass',
                                        Key=dict(slack_user=dict(S=user_id)))
        except ClientError:
            return 'You are not registered. Perhaps try \'register\' before?'
        rp = self.synel.absence_report(entry['Item']['synel_user']['S'], entry['Item']['synel_pass']['S'], absense_code,
                                       year=year)
        rt_msg = '\n'.join(['\t'.join(entry) for entry in rp])
        if not rt_msg:
            rt_msg = 'No days to report of'
        return rt_msg


if __name__ == "__main__":
    sc = SenileBot()
    sc.run_loop()
