export type TokenUser = {
  user_id: string;
  email: string;
  display_name: string;
  username?: string; // deprecated, use display_name
};

export type TokenResponse = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: TokenUser;
};

export type LoginPayload = {
  email: string;
  password: string;
};

export type RegisterPayload = {
  email: string;
  password: string;
  display_name: string;
  invite_code: string;
};
