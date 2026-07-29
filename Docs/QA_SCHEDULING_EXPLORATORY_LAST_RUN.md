# QA Exploratório — última execução

- PASS: 20
- FAIL: 0
- BUGS: 1
- NOTES: 1

## PASS
- Login tenant agendador-qa
- GET /api/v1/scheduling/professionals/ -> 200 count=1
- GET /api/v1/scheduling/services/ -> 200 count=2
- GET /api/v1/scheduling/business-hours/ -> 200 count=5
- GET /api/v1/scheduling/appointments/ -> 200 count=1
- GET /api/v1/scheduling/commission-rules/ -> 200 count=1
- POST appointment vazio -> 400 (validacao)
- Campos rejeitados no body vazio: ['customer_id', 'idempotency_key', 'professional_id', 'service_id', 'starts_at']
- POST professional sem name -> 400
- Availability 2026-07-29: 15 slots
- Agendamento no passado rejeitado -> 400
- Create appointment pending id=d8280c0d-bc41-4d7b-9c3c-ee26b64d0cd9
- Idempotency replay retorna mesmo appointment
- Overlap rejeitado -> 400
- FSM confirm -> confirmed
- FSM check-in -> checked_in
- FSM start -> in_progress
- FSM complete -> completed
- Financial após complete: price=5000
- Commission entries count=2

## FAIL
- (nenhum)

## BUGS
- POST service duration=1 -> HTTP 500 (constraint DB sem validacao serializer — UX ruim)

## NOTES
- GET professionals sem / -> 301 (redirect)
