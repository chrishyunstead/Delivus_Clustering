import aiomysql
import boto3
import pandas as pd
import pymysql


class DBHandler:
    def __init__(self):
        ssm = boto3.client("ssm")
        self.s3 = boto3.client("s3")

        # SSM 파라미터 이름 정의
        param_names = {
            "mysql_user": "/Secure/DB_USER",
            "mysql_password": "/Secure/DB_PASSWORD",
            "mysql_host": "/Secure/DW_HOST",
            "mysql_database": "/Secure/DB_DATABASE",
            "clustering_database": "/Secure/CLUSTERING_DATABASE",
        }

        # 파라미터 값 일괄 로딩
        self.mysql_user = self._get_ssm_parameter(ssm, param_names["mysql_user"])
        self.mysql_password = self._get_ssm_parameter(
            ssm, param_names["mysql_password"]
        )
        self.mysql_host = self._get_ssm_parameter(ssm, param_names["mysql_host"])
        self.mysql_database = self._get_ssm_parameter(
            ssm, param_names["mysql_database"]
        )
        self.clustering_database = self._get_ssm_parameter(
            ssm, param_names["clustering_database"]
        )
        self.mysql_port = 3306
        self.pool = None

    def _get_ssm_parameter(self, ssm, name):
        """SSM 파라미터 값을 안전하게 가져오는 함수"""
        return ssm.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]

    def fetch_data(self, database, query):
        """동기 방식 데이터 조회"""
        if database == "clustering":
            database = self.clustering_database

        try:
            conn = pymysql.connect(
                host=self.mysql_host,
                user=self.mysql_user,
                passwd=self.mysql_password,
                db=database,
                charset="utf8",
                port=self.mysql_port,
                cursorclass=pymysql.cursors.DictCursor,
            )
            with conn.cursor() as cur:
                cur.execute(query)
                results = cur.fetchall()

            df = pd.DataFrame(results)
            return df

        except Exception as e:
            print(f"Error fetching data: {e}")
            return None

        finally:
            conn.close()

    async def init_pool(self):
        if self.pool is None:
            self.pool = await aiomysql.create_pool(
                host=self.mysql_host,
                port=self.mysql_port,
                user=self.mysql_user,
                password=self.mysql_password,
                db=self.mysql_database,
                charset="utf8",
                cursorclass=aiomysql.cursors.DictCursor,
                minsize=1,
                maxsize=5,
            )

    async def fetch_data_async(self, query):
        try:
            await self.init_pool()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(query)
                    return await cur.fetchall()
        except Exception as e:
            print(f"[DBHandler] Error executing async query: {e}")
            return None
