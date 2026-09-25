export class PersonService {
  @Chunked()
  private async removePeople(ids: string[]) {
    const people = await this.personRepository.delete(ids);
    await Promise.all(people.map((person) => this.storage.unlink(person.thumbnailPath)));
  }
}
