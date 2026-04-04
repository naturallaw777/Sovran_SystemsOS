// Update the service data model to include requiresDomain and domain status fields.

class Service {
    String name;
    boolean requiresDomain;
    DomainStatus domainStatus;
}

// Enum to represent domain status health checks for services
enum DomainStatus {
    MISSING,
    MISCONFIGURED,
    CONNECTED,
    UNKNOWN
}