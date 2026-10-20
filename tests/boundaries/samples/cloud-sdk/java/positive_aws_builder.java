import software.amazon.awssdk.services.s3.S3Client;

class Storage {
    S3Client client() {
        return S3Client.builder().build();  // boundary: cloud SDK
    }
}
