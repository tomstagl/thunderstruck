package fixture;

class PositiveReadSecret {
    private final SecretClient vault;

    PositiveReadSecret(SecretClient vault) { this.vault = vault; }

    String token() {
        return vault.readSecret("secret/data/payments-api").get("token");
    }
}
