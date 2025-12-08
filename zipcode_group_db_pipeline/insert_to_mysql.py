import pandas as pd
import pymysql
from config import (
    MYSQL_DATABASE,
    MYSQL_HOST,
    MYSQL_PASSWORD,
    MYSQL_PORT,
    MYSQL_USER,
    SSH_HOST,
    SSH_PORT,
    SSH_PRIVATE_KEY,
    SSH_USER,
)
from sqlalchemy import create_engine, text
from sshtunnel import SSHTunnelForwarder

# 테이블 이름
table_name = "zipcode_groups_clone"

# 데이터 불러오기
file_name = "zipcode_groups"
df = pd.read_csv(f"{file_name}.csv")

# SSH 터널 설정
with SSHTunnelForwarder(
    (SSH_HOST, SSH_PORT),
    ssh_username=SSH_USER,
    ssh_private_key=SSH_PRIVATE_KEY,
    remote_bind_address=(MYSQL_HOST, MYSQL_PORT),
) as tunnel:
    print("SSH 터널 연결 성공!")

    # SQLAlchemy 엔진 생성
    local_mysql_port = tunnel.local_bind_port
    engine = create_engine(
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@127.0.0.1:{local_mysql_port}/{MYSQL_DATABASE}"
    )

    # zipcode group 데이터 삽입
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            for _, row in df.iterrows():
                sql = f"""
                INSERT INTO {table_name} (region, group_name, zipcodes, weekday)
                VALUES (:region, :group_name, :zipcodes, :weekday);
                """
                conn.execute(
                    text(sql),
                    {
                        "region": row["region"],
                        "group_name": row["group_name"],
                        "zipcodes": row["zipcodes"],  # JSON 그대로 저장
                        "weekday": row["weekday"],
                    },
                )
            transaction.commit()
            print("데이터 삽입 완료!")
        except Exception as e:
            transaction.rollback()
            print(f"오류 발생: {e}")
