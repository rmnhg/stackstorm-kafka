import sys
import json
from st2reactor.sensor.base import Sensor
from kafka import KafkaConsumer


class KafkaMessageSensor(Sensor):
    """
    Read multiple topics from Apache Kafka cluster and auto-commit offset (mark tasks as finished).
    If responded topic message is JSON - try to convert it to object for reuse inside st2.
    """
    TRIGGER = 'kafka.new_message'
    DEFAULT_GROUP_ID = 'st2-sensor-group'
    DEFAULT_CLIENT_ID = 'st2-kafka-consumer'

    def __init__(self, sensor_service, config=None):
        """
        Parse config variables, set defaults.
        """
        super(KafkaMessageSensor, self).__init__(sensor_service=sensor_service, config=config)
        self._logger = self._sensor_service.get_logger(__name__)

        message_sensor = self._config.get('message_sensor')
        if not message_sensor:
            raise ValueError('[KafkaMessageSensor]: "message_sensor" config value is required!')

        self._hosts = message_sensor.get('hosts')
        if not self._hosts:
            raise ValueError(
                '[KafkaMessageSensor]: "message_sensor.hosts" config value is required!')

        self._topics = set(message_sensor.get('topics', []))
        if not self._topics:
            raise ValueError(
                '[KafkaMessageSensor]: "message_sensor.topics" should list at least one topic!')

        # set defaults for empty values
        self._group_id = message_sensor.get('group_id') or self.DEFAULT_GROUP_ID
        self._client_id = message_sensor.get('client_id') or self.DEFAULT_CLIENT_ID
        self._consumer = None

    def setup(self):
        """
        Create connection and initialize Kafka Consumer.
        """
        self._logger.debug('[KafkaMessageSensor]: Initializing consumer ...')
        self._consumer = KafkaConsumer(*self._topics,
                                       client_id=self._client_id,
                                       group_id=self._group_id,
                                       bootstrap_servers=self._hosts,
                                       value_deserializer=self._try_deserialize)

    def run(self):
        """
        Run infinite loop, continuously reading for Kafka message bus,
        dispatch trigger with payload data if message received.
        """
        self._logger.debug('[KafkaMessageSensor]: Entering into listen mode ...')

        for message in self._consumer:
            # We discard messages that bounced back from our trigger
            if self.TRIGGER not in message.value:
                self._logger.debug(
                    "[KafkaMessageSensor]: Received %s:%d:%d: key=%s message=%s" %
                    (message.topic, message.partition,
                    message.offset, message.key, message.value)
                )
                topic = message.topic
                payload = {
                    'topic': topic,
                    'partition': message.partition,
                    'offset': message.offset,
                    'key': message.key,
                    'message': message.value,
                }
                self._sensor_service.dispatch(trigger=self.TRIGGER, payload=payload)
            # Mark this message as fully consumed
            #self._consumer.task_done(message)
            self._consumer.commit()

    def cleanup(self):
        """
        Close connection, just to be sure.
        """
        self._consumer.close()

    def add_trigger(self, trigger):
        pass

    def update_trigger(self, trigger):
        pass

    def remove_trigger(self, trigger):
        pass

    @staticmethod
    def _try_deserialize(body):
        """
        Try to deserialize received message body.
        Convert it to object for future reuse in st2 work chain.

        :param body: Raw message body.
        :rtype body: ``str``
        :return: Parsed message as object or original string if deserialization failed.
        :rtype: ``str|object``
        """
        try:
            body = json.loads(body)
        except Exception:
            pass

        return body
