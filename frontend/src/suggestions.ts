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

export const CUSTOMER_SUGGESTIONS: SuggestedQuestion[] = [
  {
    domain: 'customer_support',
    text: 'My toilet is occasionally leaking or running — what should I check?',
  },
  {
    domain: 'privacy',
    text: 'What personal information does Kohler collect?',
  },
  {
    domain: 'legal',
    text: 'What is the limited warranty period for model K-3901?',
  },
]

export const HR_STAFF_SUGGESTIONS: SuggestedQuestion[] = [
  ...SUGGESTIONS,
  {
    domain: 'hr',
    text: 'What is the CL leave balance for Alex Rao (EMP-1001)?',
  },
]

export const FINANCE_STAFF_SUGGESTIONS: SuggestedQuestion[] = [
  ...SUGGESTIONS,
  {
    domain: 'finance',
    text: 'What is the annual CTC for Alex Rao?',
  },
]

export function suggestionsForRole(role: string): SuggestedQuestion[] {
  switch (role) {
    case 'customer':
      return CUSTOMER_SUGGESTIONS
    case 'hr_staff':
      return HR_STAFF_SUGGESTIONS
    case 'finance_staff':
      return FINANCE_STAFF_SUGGESTIONS
    default:
      return SUGGESTIONS
  }
}

export const SUGGESTION_HINT =
  'After an answer, switch formats with the Prose / JSON / XML / Excel / Email bar — or attach a policy PDF to this chat.'
