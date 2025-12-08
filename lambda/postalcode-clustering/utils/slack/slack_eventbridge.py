import json

import boto3


class SlackEventBridge:
    def put_events(self, detail_type, slack_message_format):
        events = boto3.client("events")
        ssm = boto3.client("ssm")

        parameter_account_env = ssm.get_parameter(
            Name="/Secure/ACCOUNT_ENV", WithDecryption=True
        )
        account_env = parameter_account_env["Parameter"]["Value"]

        # put_evnets
        put_events = events.put_events(
            Entries=[
                {
                    "Source": "slack.noti",
                    "DetailType": detail_type,
                    "Detail": json.dumps(slack_message_format),
                    "EventBusName": f"{account_env}-daas-events-pushops",
                    "Resources": [],
                },
            ]
        )

        return put_events
