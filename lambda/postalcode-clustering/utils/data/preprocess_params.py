import datetime


def uuid_list_to_int(list):
    """Convert UUID list to a comma-separated integer string"""
    if len(list) == 0:
        return 0

    separtor = ","
    str = ""

    for idx, val in enumerate(list):
        str += f"""{val}{("" if idx == len(list) - 1 else separtor)}"""
    return str


def uuid_list_to_str(list):
    """Convert UUID list to a comma-separated string without hyphens"""
    separtor = ","
    str = ""

    for idx, val in enumerate(list):
        str += (
            f"""'{val.replace("-", "")}'{("" if idx == len(list) - 1 else separtor)}"""
        )
    return str


def cal_time_difference(difference_in_minute):
    """Calculate time difference based on the given minutes"""
    if difference_in_minute == 0:
        return 0

    kst_datetime = datetime.datetime.now() + datetime.timedelta(hours=9)
    cal_time = kst_datetime - datetime.timedelta(minutes=int(difference_in_minute))
    difference_time = cal_time.strftime("%Y-%m-%d %H:%M")

    return difference_time


def parse_event_params(event):
    """Extract and process key parameters from the event"""
    detail_params = event["detail"]["params"]

    return {
        "workflow_id": detail_params["workflow_id"],
        "pickup_batch_uuid_list": detail_params["pickup_batch_uuid_list"],
        "return_order_shop_uuid_list": detail_params["return_order_shop_uuid_list"],
        "difference_in_minute": detail_params[
            "shipping_timestamp_difference_in_minute"
        ]["difference_in_minute"],
        "difference_end_in_minute": detail_params[
            "shipping_timestamp_difference_in_minute"
        ]["difference_end_in_minute"],
        "shipping_shop_uuid_list": detail_params["shipping_shop_uuid_list"],
        "exclude_sector_ids": detail_params["exclude_sector_ids"],
        "delivery_date": detail_params["delivery_date"].replace("-", ""),
        "delivery_date_shop_uuid_list": detail_params["delivery_date_shop_uuid_list"],
    }
