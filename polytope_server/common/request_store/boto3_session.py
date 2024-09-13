import boto3

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from boto3.dynamodb.transform import TransformationInjector


class Serializer(TypeSerializer):
    def _serialize_float(self, value):
        return {"B": f"FL:{str(value)}".encode("utf-8")}
    
    def serialize(self, value):
        try:
            return super().serialize(value)
        except TypeError as err:
            if isinstance(value, float):
                return self._serialize_float(value)
            raise err
        

class Deserializer(TypeDeserializer):
    def _deserialize_b(self, value: bytes):
        val = value.decode("utf-8")
        if val.startswith("FL:"):
            return float(val[3:])
        return super()._deserialize_b(value)


def build_boto_session() -> boto3.Session:
    """
    Build a session object that replaces the DynamoDB serializers.

    NOTE: It's important that the registration/unregistration
          happens before any resource or client is instantiated
          from the session as those are copied based on the
          state of the session at the time of instantiating
          the client/resource.
    """
    session = boto3.Session()

    # Unregister the default Serializer
    session.events.unregister(
        event_name="before-parameter-build.dynamodb",
        unique_id="dynamodb-attr-value-input",
    )

    # Unregister the default Deserializer
    session.events.unregister(
        event_name="after-call.dynamodb",
        unique_id="dynamodb-attr-value-output",
    )

    injector = TransformationInjector(serializer=Serializer(), deserializer=Deserializer())

    # Register our serializer
    session.events.register(
        "before-parameter-build.dynamodb",
        injector.inject_attribute_value_input,
        unique_id="dynamodb-attr-value-input",
    )

    # Register our deserializer
    session.events.register(
        "after-call.dynamodb",
        injector.inject_attribute_value_output,
        unique_id="dynamodb-attr-value-output",
    )

    return session
