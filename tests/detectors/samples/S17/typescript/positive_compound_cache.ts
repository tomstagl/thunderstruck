export class UserService {
  userCache = new Map<string, User>();

  remember(u: User) {
    this.userCache.set(u.id, u);
  }
}
