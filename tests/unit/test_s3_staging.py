

from unittest import mock
from polytope_server.common.staging.s3_staging import S3Staging

from minio import Minio

@mock.patch('polytope_server.common.staging.s3_staging.Minio', autospec=True)
def test_s3_staging_secure_false(mock_minio: mock.MagicMock):
   s3_staging = S3Staging(config={})
   

   assert mock_minio.call_args_list is None

        