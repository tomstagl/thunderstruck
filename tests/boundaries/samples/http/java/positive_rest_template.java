import org.springframework.web.client.RestTemplate;

class Client {
    private final RestTemplate rest;

    Profile get(String id) {
        return rest.getForObject("https://api.example.com/users/" + id, Profile.class);  // boundary: HTTP
    }
}
