export async function register(email: string) {
  try {
    return await prisma.user.create({ data: { email } });
  } catch (e) {
    if (e.code === 'P2002') return prisma.user.findUnique({ where: { email } });
    throw e;
  }
}
