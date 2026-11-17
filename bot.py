ptb_app.add_handler(CommandHandler("start", start))
    ptb_app.add_handler(CommandHandler("myid", myid))
    ptb_app.add_handler(CommandHandler("approve", approve))
    ptb_app.add_handler(CallbackQueryHandler(button))
    ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_trx_id))
    ptb_app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, payment_screenshot))

    web_app = web.Application()
    web_app["ptb_app"] = ptb_app
    web_app.router.add_get("/", health_check)
    web_app.router.add_get("/verify-sms", verify_sms_endpoint)
    web_app.router.add_post("/verify-sms", verify_sms_endpoint)

    runner = web.AppRunner(web_app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server started on port {port}")

    await ptb_app.initialize()
    await ptb_app.start()
    await ptb_app.updater.start_polling()

    await asyncio.Event().wait()


if name == "main":
    asyncio.run(main())
