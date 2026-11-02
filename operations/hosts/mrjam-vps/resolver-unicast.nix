# Optional post-cutover correction. The qualified first release is unchanged.
# Keep the existing DNS stub/upstream configuration; stop LLMNR TCP/UDP5355.
{ ... }: {
  services.resolved.settings.Resolve.LLMNR = false;
}
