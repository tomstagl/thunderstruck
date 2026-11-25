package fixture;

class NegativeSecretShaped {
    private final SecretClient vault;

    NegativeSecretShaped(SecretClient vault) { this.vault = vault; }

    String token() {
        // return vault.readSecret("secret/data/commented").get("token");
        return vault.readSecret("AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AbCd").get("token");
    }
}
