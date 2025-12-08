import os
from dotenv import load_dotenv

# .env 파일에서 환경 변수 로드 (보안 유지)
load_dotenv()

# SSH 터널 설정
SSH_HOST = os.getenv("SSH_HOST")
SSH_PORT = int(os.getenv("SSH_PORT", 22))
SSH_USER = os.getenv("SSH_USER")
SSH_PRIVATE_KEY = os.getenv(r"SSH_PRIVATE_KEY")

# MySQL 접속 정보
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")  # SSH 터널을 사용할 경우 localhost
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")
