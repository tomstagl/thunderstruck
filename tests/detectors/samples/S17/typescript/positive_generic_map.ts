export class UserDirectory {
  private readonly byId = new Map<string, User>();

  remember(user: User) {
    this.byId.set(user.id, user);
  }
}
