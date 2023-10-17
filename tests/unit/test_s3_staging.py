

from unittest import mock
from polytope_server.common.staging.s3_staging import S3Staging

from minio import Minio

@mock.patch('polytope_server.common.staging.s3_staging.Minio', autospec=True)
def test_s3_staging_secure_false(mock_minio: mock.MagicMock):
   def callback(*args, **kwargs):
      if kwargs.get("secure") is not True:
         raise AssertionError("Secure arg value.")
      return mock.MagicMock(autospec=Minio)

   mock_minio.side_effect = callback

   S3Staging(config={})
