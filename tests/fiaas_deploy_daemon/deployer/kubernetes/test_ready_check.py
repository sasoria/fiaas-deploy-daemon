#!/usr/bin/env python
# -*- coding: utf-8

import mock
import pytest
from monotonic import monotonic as time_monotonic

from fiaas_deploy_daemon.deployer.bookkeeper import Bookkeeper
from fiaas_deploy_daemon.deployer.kubernetes.ready_check import ReadyCheck
from fiaas_deploy_daemon.lifecycle import Lifecycle
from fiaas_deploy_daemon.specs.models import LabelAndAnnotationSpec
from k8s.models.deployment import Deployment

REPLICAS = 2


class TestReadyCheck(object):
    @pytest.fixture
    def bookkeeper(self):
        return mock.create_autospec(Bookkeeper, spec_set=True)

    @pytest.fixture
    def lifecycle(self):
        return mock.create_autospec(Lifecycle, spec_set=True)

    @pytest.fixture
    def deployment(self):
        with mock.patch("k8s.models.deployment.Deployment.get") as m:
            deployment = mock.create_autospec(Deployment(), spec_set=True)
            deployment.spec.replicas.return_value = REPLICAS
            m.return_value = deployment
            return deployment

    def test_deployment_complete(self, get, app_spec, bookkeeper, lifecycle):
        self._create_response(get)

        ready = ReadyCheck(app_spec, bookkeeper, lifecycle)

        assert ready() is False
        bookkeeper.success.assert_called_with(app_spec)
        bookkeeper.failed.assert_not_called()

    @pytest.mark.parametrize("requested,replicas,available,updated", (
            (8, 9, 7, 2),
            (2, 2, 1, 2),
            (2, 2, 2, 1),
            (2, 1, 1, 1)
    ))
    def test_deployment_incomplete(self, get, app_spec, bookkeeper, requested, replicas, available, updated,
                                   lifecycle):
        self._create_response(get, requested, replicas, available, updated)

        ready = ReadyCheck(app_spec, bookkeeper, lifecycle)

        assert ready() is True
        bookkeeper.success.assert_not_called()
        bookkeeper.failed.assert_not_called()
        lifecycle.success.assert_not_called()
        lifecycle.failed.assert_not_called()

    @pytest.mark.parametrize("requested,replicas,available,updated,annotations,repository", (
            (8, 9, 7, 2, None, None),
            (2, 2, 1, 2, None, None),
            (2, 2, 2, 1, None, None),
            (2, 1, 1, 1, None, None),
            (2, 1, 1, 1, {"fiaas/source-repository": "xyz"}, "xyz"),
    ))
    def test_deployment_failed(self, get, app_spec, bookkeeper, requested, replicas, available, updated,
                               lifecycle, annotations, repository):
        if annotations:
            app_spec = app_spec._replace(annotations=LabelAndAnnotationSpec(*[annotations] * 5))

        self._create_response(get, requested, replicas, available, updated)

        ready = ReadyCheck(app_spec, bookkeeper, lifecycle)
        ready._fail_after = time_monotonic()

        assert ready() is False
        bookkeeper.success.assert_not_called()
        bookkeeper.failed.assert_called_with(app_spec)
        lifecycle.success.assert_not_called()
        lifecycle.failed.assert_called_with(app_name=app_spec.name, namespace=app_spec.namespace,
                                            deployment_id=app_spec.deployment_id, repository=repository)

    @staticmethod
    def _create_response(get, requested=REPLICAS, replicas=REPLICAS, available=REPLICAS, updated=REPLICAS):
        get.side_effect = None
        resp = mock.MagicMock()
        get.return_value = resp
        resp.json.return_value = {
            'metadata': pytest.helpers.create_metadata('testapp'),
            'spec': {
                'selector': {'matchLabels': {'app': 'testapp'}},
                'template': {
                    'spec': {
                        'containers': [{
                            'name': 'testapp',
                            'image': 'finntech/testimage:version',
                        }]
                    },
                    'metadata': pytest.helpers.create_metadata('testapp')
                },
                'replicas': requested
            },
            'status': {
                'replicas': replicas,
                'availableReplicas': available,
                'unavailableReplicas': replicas - available,
                'updatedReplicas': updated
            }
        }
