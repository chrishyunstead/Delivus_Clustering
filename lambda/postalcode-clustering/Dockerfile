FROM public.ecr.aws/lambda/python:3.10
COPY app.py requirements.txt ./
COPY utils/ ./utils/
COPY template/ ./template/ 
RUN pip install --upgrade pip && pip install -r requirements.txt
CMD ["app.lambda_handler"]