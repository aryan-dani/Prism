export type SuggestedQuestion = {
  text: string
  domain: string
}

/** Curated empty-state / landing prompts — chosen because they hit deterministic
 *  or well-covered paths (policy_math, Assist leak article, privacy policy, table). */
export const SUGGESTIONS: SuggestedQuestion[] = [
  {
    domain: 'finance',
    text: 'An employee submits an expense claim for ₹15,000. Who needs to approve it?',
  },
  {
    domain: 'hr',
    text: 'How many casual leave days can I carry forward?',
  },
  {
    domain: 'customer_support',
    text: 'My toilet is occasionally leaking or running — what should I check?',
  },
  {
    domain: 'privacy',
    text: 'What personal information does Kohler collect?',
  },
  {
    domain: 'finance',
    text: 'Compare the domestic per diem for Pune versus a smaller city like Jaipur.',
  },
]

export const SUGGESTION_HINT =
  'Then try: “give that as JSON” — or attach a policy PDF to this chat.'
