"""Section 14 base package: context, registration loading, and specs."""

from subsystem_sdk.base.config import (
    load_registration_spec,
    load_submit_backend_config,
)
from subsystem_sdk.base.context import BaseSubsystemContext
from subsystem_sdk.base.registration import (
    RegistrationError,
    RegistrationRegistry,
    SubsystemRegistrationSpec,
    get_registered_subsystem,
    register_subsystem,
)
from subsystem_sdk.base.runtime import RuntimeNotConfiguredError, configure_runtime
from subsystem_sdk.base.scaffold import (
    ReferenceSubsystemTemplate,
    create_reference_subsystem,
)
from subsystem_sdk.base.subsystem import BaseSubsystem, SubsystemBaseInterface

__all__ = [
    "SubsystemRegistrationSpec",
    "RegistrationRegistry",
    "RegistrationError",
    "register_subsystem",
    "get_registered_subsystem",
    "load_registration_spec",
    "load_submit_backend_config",
    "BaseSubsystemContext",
    "RuntimeNotConfiguredError",
    "configure_runtime",
    "ReferenceSubsystemTemplate",
    "create_reference_subsystem",
    "SubsystemBaseInterface",
    "BaseSubsystem",
]
