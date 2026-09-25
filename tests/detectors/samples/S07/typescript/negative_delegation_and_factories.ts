export class AlbumController {
  constructor(private service: AlbumService) {}

  create(auth: Auth, dto: CreateAlbumDto) {
    return this.service.create(auth, dto);
  }
}

export async function bootstrap() {
  const app = await NestFactory.create(AppModule, { bufferLogs: true });
  const config = BaseConfig.create(settings);
  const headers = PlaylistHeaderDto.create(raw);
  const hasher = sha1.create();
  return { app, config, headers, hasher };
}
