import pandas as pd
import pymysql
from sshtunnel import SSHTunnelForwarder
from sqlalchemy import create_engine, text
from config import (
    SSH_HOST,
    SSH_PORT,
    SSH_USER,
    SSH_PRIVATE_KEY,
    MYSQL_HOST,
    MYSQL_PORT,
    MYSQL_USER,
    MYSQL_PASSWORD,
    MYSQL_DATABASE,
)

# 데이터 불러오기
file_name = "sector_divided"
df = pd.read_csv(f"output/{file_name}.csv")

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
                sql = """
                INSERT INTO sector_divided (region, zipcodes)
                VALUES (:region, :zipcodes);
                """
                conn.execute(
                    text(sql),
                    {
                        "region": row["region"],
                        "zipcodes": row["zipcodes"],  # JSON 그대로 저장
                    },
                )
            transaction.commit()
            print("데이터 삽입 완료!")
        except Exception as e:
            transaction.rollback()
            print(f"오류 발생: {e}")
