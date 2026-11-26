export function cn(
  ...inputs: Array<string | number | false | null | undefined>
): string {
  return inputs.filter((v): v is string | number => Boolean(v)).join(" ");
}
