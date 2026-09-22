export async function profile(id: string) {
  const [user, prefs] = await Promise.all([getUser(id), getPrefs(id)]);
  return { user, prefs };
}
