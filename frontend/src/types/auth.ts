export type TokenUser = {
  username: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: TokenUser;
};

export type LoginPayload = {
  username: string;
  password: string;
};
