import type { GetServerSideProps } from "next";

export default function HomeRedirect() {
  return null;
}

export const getServerSideProps: GetServerSideProps = async () => {
  return {
    redirect: {
      destination: "/missions",
      permanent: false,
    },
  };
};
