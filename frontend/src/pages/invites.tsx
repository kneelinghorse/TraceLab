import type { GetServerSideProps } from "next";

export const getServerSideProps: GetServerSideProps = async () => ({
  redirect: { destination: "/settings#invites", permanent: false },
});

export default function InvitesPage() {
  return null;
}
