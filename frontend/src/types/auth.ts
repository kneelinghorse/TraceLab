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

export type RegisterPayload = {
  email: string;
  password: string;
  display_name?: string;
};
