"""Local printer protocol adapters."""

from ufm.integrations.printers.bambu_lan import BambuLanProvider, feed_systems_from_report
from ufm.integrations.printers.bambu_studio import (
    BambuStudioImportError,
    BambuStudioProfile,
    import_bambu_studio_profile,
    store_bambu_root_certificate,
)
from ufm.integrations.printers.configuration import (
    ConfiguredLocalPrinter,
    ConfiguredPrinterObservation,
    PrinterConfigurationError,
    configure_bambu_printer,
    configure_local_printer,
    ensure_local_device,
    local_provider,
    probe_configured_printer,
    remove_configured_printer,
)
from ufm.integrations.printers.discovery import (
    PrinterCandidate,
    PrinterDiscoveryError,
    discover_printers,
    primary_local_network,
)
from ufm.integrations.printers.local_http import (
    LocalPrinterHttpProvider,
    MoonrakerProvider,
    OctoPrintProvider,
)

__all__ = [
    "ConfiguredLocalPrinter",
    "ConfiguredPrinterObservation",
    "BambuLanProvider",
    "BambuStudioImportError",
    "BambuStudioProfile",
    "LocalPrinterHttpProvider",
    "MoonrakerProvider",
    "OctoPrintProvider",
    "PrinterConfigurationError",
    "PrinterCandidate",
    "PrinterDiscoveryError",
    "configure_local_printer",
    "configure_bambu_printer",
    "discover_printers",
    "feed_systems_from_report",
    "import_bambu_studio_profile",
    "ensure_local_device",
    "local_provider",
    "primary_local_network",
    "probe_configured_printer",
    "remove_configured_printer",
    "store_bambu_root_certificate",
]
