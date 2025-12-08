class ZipCodeGroupProcessor:
    def __init__(self, db_handler):
        """Class for processing Zip Code groups"""
        self.db_handler = db_handler

    def fetch_all_data(self):
        """Fetches Zip Code group-related data from MySQL"""
        queries = {
            "df_regular": "SELECT region, group_name, zipcodes FROM clustering.zipcode_groups_polygon WHERE weekday = 0;",
            "df_weekend": "SELECT region, group_name, zipcodes FROM clustering.zipcode_groups_polygon WHERE weekday = 1;",
        }

        df_results = {
            key: self.db_handler.fetch_data(query) for key, query in queries.items()
        }

        return df_results
