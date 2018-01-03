import os
import time
import re
import pdb
import boto3
import requests
from slackclient import SlackClient
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





class SenileBot(object):
    RTM_READ_DELAY = 1  # 1 second delay between reading from RTM
    MENTION_REGEX = "^<@(|[WU].+)>(.*)"
    USERS_URL = 'https://slack.com/api/users.list'

    def __init__(self):
        self.app_token = os.environ.get('SLACK_BOT_TOKEN')
        self.slack_client = SlackClient(self.app_token)
        self.bot_id = None
        self.available_commands = {
            'register': self.register_user,
        }  # type: dict[(), ()]
        self.connect()

        self.dyndb = boto3.client('dynamodb', endpoint_url='http://{}:{}'.format('192.168.206.41', '8081'),
                                  iguazio_management_url='http://{}:{}'.format('192.168.202.16', '8001'),
                                  is_iguazio_api=True, iguazio_management_username='iguazio',
                                  iguazio_management_password='Password1', region_name='lala')

        response = requests.get('http://{}:{}/{}?prefix=/{}/'.format('192.168.206.41', '8081', '1', 'registered_users'))
        if response.status_code >= '400':
            self.dyndb.create_table(TableName='registered_users',
                                    Bucket='1',
                                    KeySchema=[{'AttributeName': 'slack_user', 'KeyType': 'HASH'}])
        if not self.bot_id:
            raise RuntimeError('Failed connecting to slack.')

    def slack_users_list(self):
        response = requests.get('{}?token='.format(self.USERS_URL, self.app_token))
        response.raise_for_status()
        return response.content

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
        command_syntax = "Syntax: register <synel_user> <synel_password>"
        match = re.search(r'(\d+)\s+(\S+)$', command_text)
        if not match:
            return 'Wrong syntax. {}'.format(command_syntax)
        self.dyndb.put_item(TableName='registered_users', Bucket='1', validate_exists=False,
                            Item=dict(slack_user=dict(S=user_id),
                                      synel_user=dict(S=match.group(1)),
                                      synel_pass=dict(S=match.group(2))))
        return 'Registered user {} with password {}'.format(match.group(1), match.group(2))



if __name__ == "__main__":
    sc = SenileBot()
    sc.run_loop()
