// Roles mirror app/core/security.py. Human roles are cumulative
// (owner ⊇ admin ⊇ member ⊇ viewer); "service" is outside that hierarchy.
// Role is NEVER stored in TokenUser/StoredAuth/the JWT (decision #226 + #313);
// the client learns its role only from a live GET /auth/me (see RoleContext).
export type Role = "owner" | "admin" | "member" | "viewer" | "service";

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
