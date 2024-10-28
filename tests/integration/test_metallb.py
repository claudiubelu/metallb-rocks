#
# Copyright 2024 Canonical, Ltd.
# See LICENSE file for licensing details
#

from k8s_test_harness import harness
from k8s_test_harness.util import constants, env_util, k8s_util
from k8s_test_harness.util.k8s_util import HelmImage

IMG_PLATFORM = "amd64"
INSTALL_NAME = "metallb"


def _get_rock_image(name: str, version: str):
    rock = env_util.get_build_meta_info_for_rock_version(name, version, IMG_PLATFORM)
    return rock.image


def _get_logs(
    instance: harness.Instance,
    resource_type: str,
    resource: str,
    namespace=constants.K8S_NS_KUBE_SYSTEM,
):
    process = instance.exec(
        [
            "k8s",
            "kubectl",
            "logs",
            "-n",
            namespace,
            f"{resource_type}/{resource}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return process.stdout


def test_metallb_0_14_5(function_instance: harness.Instance):
    images = [
        HelmImage(
            uri=_get_rock_image("metallb-controller", "v0.14.5"), prefix="controller"
        ),
        HelmImage(uri=_get_rock_image("metallb-speaker", "v0.14.5"), prefix="speaker"),
        HelmImage(uri=_get_rock_image("frr", "9.0.2"), prefix="frr"),
    ]

    # We need to run frr as root because of:
    # https://bugzilla.redhat.com/show_bug.cgi?id=2147522
    helm_command = k8s_util.get_helm_install_command(
        name=INSTALL_NAME,
        chart_name="metallb",
        images=images,
        namespace=constants.K8S_NS_KUBE_SYSTEM,
        repository="https://metallb.github.io/metallb",
        chart_version="v0.14.5",
        runAsUser=0,
    )
    helm_command += [
        "--set",
        "controller.securityContext.fsGroup=0",
        "--set",
        "controller.securityContext.runAsNonRoot=false",
        "--set",
        "controller.command=/controller",
        "--set",
        "speaker.command=/speaker",
    ]
    function_instance.exec(helm_command)

    k8s_util.wait_for_daemonset(
        function_instance, "metallb-speaker", constants.K8S_NS_KUBE_SYSTEM
    )

    k8s_util.wait_for_deployment(
        function_instance, "metallb-controller", constants.K8S_NS_KUBE_SYSTEM
    )

    # Sanity check: make sure there isn't an error in Pebble that it couldn't start the service.
    logs = _get_logs(function_instance, constants.K8S_DEPLOYMENT, "metallb-controller")
    assert '(Start service "controller") failed' not in logs

    logs = _get_logs(function_instance, constants.K8S_DAEMONSET, "metallb-speaker")
    assert '(Start service "controller") failed' not in logs
