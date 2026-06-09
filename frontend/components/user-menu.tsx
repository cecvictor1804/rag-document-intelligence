// Server component: reads the session and renders the user menu in the header.
// Renders nothing when auth is disabled or no one is signed in.

import { authEnabled } from "@/lib/auth/config";
import { getSession } from "@/lib/auth/session";

import { UserMenuClient } from "./user-menu-client";

export async function UserMenu() {
  if (!authEnabled) return null;
  const session = await getSession();
  if (!session) return null;

  return <UserMenuClient email={session.email} name={session.name} />;
}
