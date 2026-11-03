// One bounded access snapshot in process memory, never a shared refresh credential.
export function subscriptionCredentials(credential) {
  if (!credential?.access || credential.refresh || credential.type !== "oauth") throw new Error("Invalid subscription snapshot");
  return {
    async read(id) { return id === "openai-codex" ? credential : undefined; },
    async list() { return [{providerId:"openai-codex",type:"oauth"}]; },
    async modify(id, fn) {
      if (id !== "openai-codex") throw new Error("Unregistered credential provider");
      const updated = await fn(credential);
      if (updated) credential = updated;
      return credential;
    },
    async delete() { throw new Error("Subscription snapshot is not a login manager"); },
  };
}
