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

# 데이터 불러오기
df = pd.read_csv("output/geojson_data.csv", dtype={"BAS_ID": str})

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

    # 테이블 생성 (존재하지 않으면)
    create_table_query = """
    CREATE TABLE IF NOT EXISTS geojson_features_test (
        id INT AUTO_INCREMENT PRIMARY KEY,
        bas_id VARCHAR(50) NOT NULL,
        bas_ar DECIMAL(10,6) DEFAULT NULL,
        bas_mgt_sn VARCHAR(50) DEFAULT NULL,
        ctp_kor_nm VARCHAR(100) DEFAULT NULL,
        sig_cd VARCHAR(20) DEFAULT NULL,
        sig_kor_nm VARCHAR(100) DEFAULT NULL,
        ntfc_de DATE DEFAULT NULL,
        geometry GEOMETRY NULL SRID 4326
    );
    """
    with engine.connect() as conn:
        conn.execute(text(create_table_query))

    # pd.to_sql()을 사용하여 데이터 삽입 (geometry 제외)
    df.drop(columns=["geometry"]).to_sql(
        "geojson_features_test", con=engine, if_exists="append", index=False
    )

    # 공간 데이터(geometry) 필드는 별도로 삽입
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            for idx, row in df.iterrows():
                print(row)
                sql = """
                UPDATE geojson_features_test
                SET geometry = ST_GeomFromText(:geom, 4326)
                WHERE bas_id = :bas_id;
                """
                conn.execute(
                    text(sql), {"geom": row["geometry"], "bas_id": row["BAS_ID"]}
                )

                # 한 줄 실행 후 즉시 커밋
                transaction.commit()
                # 다음 트랜잭션 시작
                transaction = conn.begin()

            print("모든 데이터 삽입 완료!")

        except Exception as e:
            transaction.rollback()  # 에러 발생 시 롤백
            print(f"에러 발생: {e}")
