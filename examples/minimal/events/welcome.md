---
event_id: welcome
title: 第一次找书
target_stage: first_meeting
is_repeatable: false
guard:
  flags_required:
    welcome_done: false
pool:
  priority: 100
  condition:
    all:
      - path: scene.location
        value: bookshop
      - path: scene.activity
        value: browsing
lifecycle:
  on_success_condition: helped === true
  on_success_mutation:
    relation_stage: familiar
    trust: "+= 5"
    flags:
      welcome_done: true
    completed_events: [welcome]
  on_fail_condition: declined === true
  on_fail_mutation: {}
---
店员问 {{user}} 是否需要找书建议。由用户决定接受还是自己逛，不替用户回答。
用户接受建议并完成这次交流后才算成功；拒绝帮助时自然结束，不扣分，也不阻止继续聊天。
