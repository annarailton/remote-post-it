export const OWNER_EMAIL = 'anna.railton@gmail.com';

export function isOwner(claims) {
  return claims?.email === OWNER_EMAIL
    && claims.email_verified === true
    && claims.firebase?.sign_in_provider === 'google.com';
}
