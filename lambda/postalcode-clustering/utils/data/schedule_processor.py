class ScheduleProcessor:
    def __init__(self, db_handler):
        """Class for processing schedule data"""
        self.db_handler = db_handler

    def fetch_schedules(self, workflow_date):
        """Fetches schedule data for a specific date"""
        query = f"""
            SELECT 
				'user_uuid' as 'uuid',
                dispatch_dataset.requested_date as 'Date',
                dispatch_dataset.bunny_color as 'Type',
                location_sector.code as 'code',
                dispatch_dataset.dispatch_status as 'dispatch_status',
                REPLACE(regexp_replace(location_sector.code, '[0-9]', ''), '_', '') as 'Area'
            FROM location_sector 
            JOIN (
                SELECT 
                    dispatch_dispatch.requested_date as 'requested_date',
                    dispatch_schedule.bunny_color as 'bunny_color', 
                    JSON_EXTRACT(dispatch_dispatch.sector_list, '$[0]') as 'sector_id',
                    dispatch_dispatch.user_id as 'user_id',
                    dispatch_dispatch.dispatch_status as 'dispatch_status'
                FROM dispatch_dispatch
                JOIN dispatch_schedule
                ON dispatch_dispatch.schedule_id = dispatch_schedule.id
                WHERE dispatch_dispatch.schedule_id IS NOT NULL
                AND dispatch_dispatch.dispatch_status = 'SUBMITTED'
                AND dispatch_dispatch.requested_date = '{workflow_date}'
            ) dispatch_dataset
            ON location_sector.id = dispatch_dataset.sector_id
        """
        return self.db_handler.fetch_data("daas", query)
