---
event_id: restock
title: 一起整理书架
target_stage: familiar
is_repeatable: true
guard:
  completed_events_required: [welcome]
pool:
  priority: 10
  cooldown_turns: 2
  condition:
    all:
      - path: scene.location
        value: bookshop
      - path: scene.activity
        value: sorting
lifecycle:
  on_success_condition: sorted === true
  on_success_mutation:
    trust: "+= 1"
    completed_events: [restock]
  on_fail_condition: false === true
  on_fail_mutation: {}
  branches:
    pause:
      condition: paused === true
      mutation: {}
---
店员在整理柜台旁的书，{{user}}可以选择帮忙。两人可以边整理边聊，也可以暂时停下。
只有用户确实动手并完成整理才算成功。用户提出暂停时走 pause 分支，不把暂停记作完成。
