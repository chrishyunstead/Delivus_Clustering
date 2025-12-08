import datetime
import json


class CreateSlackTemplate:
    def open_json_file(self):
        with open(f"template/head.json") as data_file:
            file = json.load(data_file)
        return file

    def create_head_template(self, head_title):
        head_template = self.open_json_file()

        datetime_now_datetime = datetime.datetime.now() + datetime.timedelta(hours=9)
        current_datetime = datetime_now_datetime.strftime("%y/%m/%d %H:%M:%S")

        head_template["params"]["slack_format"]["blocks"][0]["text"][
            "text"
        ] = head_title
        head_template["params"]["slack_format"]["blocks"][1]["elements"][0][
            "text"
        ] = f"{current_datetime} | Delivus Team Announcements"

        return head_template

    def create_section_template(self, section_text):
        section_template = {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"{section_text}"},
        }
        return section_template

    def create_divider_template(self):
        divider = {"type": "divider"}
        return divider
