# Example: the approved reel

## script.txt
```
Hook (0-5s): Stop adding more database servers when your app slows down; you're just burning money on the wrong bottleneck.
Body (5-20s): When 100,000 users hit your login simultaneously, your relational database locks up because disk I/O can’t keep pace. Instead, place an in-memory Redis cache in front to serve hot data in sub-milliseconds, and put write requests into a message queue like Kafka to process them at a steady pace.
CTA (20-30s): Caching handles read spikes, queues smooth write spikes—save this architectural pattern for your next system design interview!
```

## make_phrases.py output (phrase numbers used in example_spec.json)
```
p0: *Stop* adding more
p1: *database* *servers*
p2: when your app
p3: *slows* *down*
p4: you're just *burning* *money*
p5: on the *wrong* *bottleneck*
p6: When *100,000* users hit
p7: your login *simultaneously*
p8: your *relational* *database*
p9: *locks* *up*
p10: because *disk* *I/O*
p11: *can’t* *keep* *pace*
p12: *Instead*
p13: place an in-memory
p14: *Redis* *cache* in front
p15: to serve *hot* *data*
p16: in *sub-milliseconds*
p17: and put *write* *requests*
p18: into a *message* *queue*
p19: like *Kafka*
p20: to process them
p21: at a *steady* *pace*
p22: *Caching* handles *read* *spikes*
p23: *queues* smooth *write* *spikes*
p24: *save*
p25: this *architectural* *pattern*
p26: for your next
p27: *system* *design* *interview!*
28 phrases, 85 words
```
