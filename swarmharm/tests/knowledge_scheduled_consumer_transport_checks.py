"""Reuse the scripted native transport check for Knowledge subscriptions."""
from tests import data_scheduled_consumer_transport_checks as base


class KnowledgeScheduledTransportChecks(base.DataScheduledTransportChecks):
    domain='knowledge-work'
    variant='knowledge-scheduled-consumer-v1'
