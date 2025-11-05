import { createHash } from 'crypto';

export const sha256 = (input: string): string => {
  const hash = createHash('sha256');
  hash.update(input);
  return hash.digest('hex');
};

export const stableId = (namespace: string, value: string): string => {
  return createHash('sha1')
    .update(namespace)
    .update(':')
    .update(value)
    .digest('hex');
};
