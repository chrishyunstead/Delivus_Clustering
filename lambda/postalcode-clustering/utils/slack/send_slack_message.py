from .create_slack_template import CreateSlackTemplate
from .slack_eventbridge import SlackEventBridge


class SendSlackMessage:
    def __init__(self):
        self.init = None

    def send_start_slack_message(
        self,
        workflow_id,
        ACCOUNT_ENV,
    ):
        base_template = CreateSlackTemplate().create_head_template(
            f":post_office: [Postalcode-Clustering] Starting {workflow_id}"
        )
        divider = CreateSlackTemplate().create_divider_template()
        base_template_body = base_template["params"]["slack_format"]["blocks"]
        account_env_section = CreateSlackTemplate().create_section_template(
            f"`실행 환경` *{ACCOUNT_ENV}*"
        )
        base_template_body.extend([account_env_section, divider])

        SlackEventBridge().put_events("#d_staff-ops", base_template)

    def send_end_slack_message(self, workflow_id, ACCOUNT_ENV, cluster_items_count):
        base_template = CreateSlackTemplate().create_head_template(
            f":postbox:  [Postalcode-Clustering] Completed {workflow_id}"
        )
        divider = CreateSlackTemplate().create_divider_template()
        base_template_body = base_template["params"]["slack_format"]["blocks"]
        account_env_section = CreateSlackTemplate().create_section_template(
            f"`실행 환경` *{ACCOUNT_ENV}*"
        )
        cluster_num_section = CreateSlackTemplate().create_section_template(
            f"`클러스터링된 배송 아이템 수` *{cluster_items_count}*"
        )
        base_template_body.extend(
            [
                account_env_section,
                cluster_num_section,
                divider,
            ]
        )

        SlackEventBridge().put_events("#d_staff-ops", base_template)

    def send_lat_alert_slack_message(
        self,
        workflow_id,
        ACCOUNT_ENV,
        lat_null_count,
    ):
        base_template = CreateSlackTemplate().create_head_template(
            f":quack_alert:  [Postalcode-Clustering] {workflow_id} 위경도값 없음"
        )
        divider = CreateSlackTemplate().create_divider_template()
        base_template_body = base_template["params"]["slack_format"]["blocks"]
        account_env_section = CreateSlackTemplate().create_section_template(
            f"`실행 환경` *{ACCOUNT_ENV}*"
        )
        lat_count_section = CreateSlackTemplate().create_section_template(
            f"`위경도값 없는 데이터 수` *{lat_null_count}*"
        )
        base_template_body.extend([account_env_section, divider])

        SlackEventBridge().put_events("#d_staff-ops", base_template)
