// jscs:disable requireCapitalizedConstructors

define([
        'jquery',
        'backbone',
        'backbone.super',
        'backbone.validation',
        'backbone.stickit',
        'ecommerce',
        'underscore',
        'underscore.string',
        'utils/utils',
        'text!templates/coupon_form.html',
        'models/course_model',
        'views/form_view'
    ],
    function ($,
              Backbone,
              BackboneSuper,
              BackboneValidation,
              BackboneStickit,
              ecommerce,
              _,
              _s,
              Utils,
              CouponFormTemplate,
              Course,
              FormView) {
        'use strict';

        return FormView.extend({
            tagName: 'form',

            className: 'coupon-form-view',

            template: _.template(CouponFormTemplate),

            seatTypes: [],

            codeTypes: [
                {
                    value: 'Enrollment code',
                    label: gettext('Enrollment Code')
                },
                {
                    value: 'Discount code',
                    label: gettext('Discount Code')
                }
            ],

            voucherTypes: [
                {
                    value: 'Single use',
                    label: gettext('Can be used once by one customer')
                },
                {
                    value: 'Once per customer',
                    label: gettext('Can be used once by multiple customers')
                }
            ],

            bindings: {
                'select[name=category]': {
                    observe: 'category',
                    selectOptions: {
                        collection: function () {
                            return ecommerce.coupons.categories;
                        },
                        labelPath: 'name',
                        valuePath: 'id'
                    },
                    setOptions: {
                        validate: true
                    }
                },
                'input[name=title]': {
                    observe: 'title'
                },
                'select[name=code_type]': {
                    observe: 'coupon_type',
                    selectOptions: {
                        collection: function () {
                            return this.codeTypes;
                        }
                    }
                },
                'select[name=voucher_type]': {
                    observe: 'voucher_type',
                    selectOptions: {
                        collection: function () {
                            return this.voucherTypes;
                        }
                    }
                },
                'input[name=benefit_type]': {
                    observe: 'benefit_type',
                    onGet: function (val) {
                        if (val === 'Percentage') {
                            return val;
                        } else if (val === 'Absolute') {
                            return 'Absolute';
                        }
                        return '';
                    }
                },
                '.benefit-addon': {
                    observe: 'benefit_type',
                    onGet: function (val) {
                        if (val === 'Percentage') {
                            return '%';
                        } else if (val === 'Absolute') {
                            return '$';
                        }
                        return '';
                    }
                },
                'input[name=benefit_value]': {
                    observe: 'benefit_value'
                },
                'input[name=client]': {
                    observe: 'client'
                },
                'input[name=course_id]': {
                    observe: 'course_id'
                },
                'input[name=quantity]': {
                    observe: 'quantity'
                },
                'input[name=price]': {
                    observe: 'price'
                },
                'input[name=total_value]': {
                    observe: 'total_value'
                },
                'input[name=start_date]': {
                    observe: 'start_date',
                    onGet: function (val) {
                        return Utils.stripTimezone(val);
                    }
                },
                'input[name=end_date]': {
                    observe: 'end_date',
                    onGet: function (val) {
                        return Utils.stripTimezone(val);
                    }
                },
                'input[name=code]': {
                    observe: 'code'
                },
                'input[name=note]': {
                    observe: 'note'
                },
                'input[name=max_uses]': {
                    observe: 'max_uses'
                },
                'input[name=catalog_type]': {
                    observe: 'catalog_type'
                },
                'textarea[name=catalog_query]': {
                    observe: 'catalog_query'
                },
                'input[name=course_seats]': {
                    observe: 'course_seats'
                },
            },

            events: {
                'click [name=preview_catalog]': 'previewCatalog',
                'click [name=catalog_help]': 'getHelpWithCatalog',

                'input [name=course_id]': 'fillFromCourse',
                'input [name=quantity]': 'changeTotalValue',

                // catch value after autocomplete
                'blur [name=course_id]': 'fillFromCourse',
                'change [name=seat_type]': 'changeSeatType',
                'change [name=benefit_type]': 'changeUpperLimitForBenefitValue',
            },

            initialize: function (options) {
                this.alertViews = [];
                this.editing = options.editing || false;

                this.listenTo(this.model, 'change:coupon_type', this.toggleFields);
                this.listenTo(this.model, 'change:voucher_type', this.toggleFields);
                this.listenTo(this.model, 'change:catalog_type', this.toggleFields);

                this._super();
            },

            changeUpperLimitForBenefitValue: function () {
                var is_benefit_percentage = this.$el.find('[name=code_type]').val() === 'Percentage',
                    max_value = is_benefit_percentage ? '100' : '';

                this.$el.find('[name=benefit_value]').attr('max', max_value);
            },

            toggleFields: function () {
                var hiddenClass = 'hidden';
                var couponType = this.model.get('coupon_type'),
                    voucherType = this.model.get('voucher_type'),
                    catalog_type = this.model.get('catalog_type'),
                    formGroup = function (sel) {
                        return this.$el.find(sel).closest('.form-group');
                    }.bind(this);

                if (catalog_type === 'Single course') {
                    formGroup('[name=catalog_query]').addClass(hiddenClass);
                    formGroup('[name=course_seats]').addClass(hiddenClass);
                    formGroup('[name=course_id]').removeClass(hiddenClass);
                    formGroup('[name=seat_type]').removeClass(hiddenClass);
                } else {
                    formGroup('[name=catalog_query]').removeClass(hiddenClass);
                    formGroup('[name=course_seats]').removeClass(hiddenClass);
                    formGroup('[name=course_id]').addClass(hiddenClass);
                    formGroup('[name=seat_type]').addClass(hiddenClass);
                }

                if (couponType === 'Discount code') {
                    formGroup('[name=benefit_value]').removeClass(hiddenClass);
                } else {
                    // enrollment
                    formGroup('[name=benefit_value]').addClass(hiddenClass);
                }

                // When creating a discount show the CODE field for both (they are both multi-use)
                //     - Multiple times by multiple customers
                //     - Once per customer
                if (couponType === 'Discount code' && voucherType !== 'Single use') {
                    formGroup('[name=code]').removeClass(hiddenClass);
                } else {
                    formGroup('[name=code]').addClass(hiddenClass);
                }

                // When creating a Once by multiple customers code show the usage number field.
                // The only time we allow for a generation of multiple codes is
                // when they are of type single use.
                if (voucherType === 'Single use') {
                    formGroup('[name=quantity]').removeClass(hiddenClass);
                    formGroup('[name=max_uses]').addClass(hiddenClass);
                } else {
                    formGroup('[name=max_uses]').removeClass(hiddenClass);
                    formGroup('[name=quantity]').addClass(hiddenClass);
                }
            },

            /**
             * Fill seat type options from course ID.
             */
            fillFromCourse: _.debounce(function () {
                var courseId = this.$el.find('[name=course_id]').val(),
                    course = Course.findOrCreate({id: courseId}),
                    parseId = _.compose(parseInt, _.property('id'));

                // stickit will not pick it up if this is a blur event
                this.model.set('course_id', courseId);

                course.listenTo(course, 'sync', _.bind(function () {
                    this.seatTypes = _.map(course.seats(), function (seat) {
                        var name = seat.getSeatTypeDisplayName();
                        return $('<option></option>')
                            .text(name)
                            .val(name)
                            .data({
                                price: seat.get('price'),
                                stockrecords: _.map(seat.get('stockrecords'), parseId)
                            });
                    });
                    // update field
                    this.$el.find('[name=seat_type]')
                        .html(this.seatTypes)
                        .trigger('change');

                    if (this.editing) {
                        this.$el.find('[name=seat_type]')
                            .val(_s.capitalize(this.model.get('seat_type')));
                    }
                }, this));

                course.fetch({data: {include_products: true}});
            }, 100),

            /*
             * Update price field and model.stockrecords
             */
            changeSeatType: function () {
                var seatType = this.getSeatType(),
                    seatData = this.getSeatData();

                if (!this.editing) {
                    this.model.set('seat_type', seatType);

                    if (seatType && !this.editing) {
                        this.model.set('stock_record_ids', seatData.stockrecords);
                        this.updateTotalValue(seatData);
                    }
                }
            },

            changeTotalValue: function () {
                this.updateTotalValue(this.getSeatData());
            },

            updateTotalValue: function (seatData) {
                var quantity = this.$el.find('input[name=quantity]').val(),
                    totalValue = quantity * seatData.price;
                this.model.set('total_value', totalValue);
                this.$el.find('input[name=price]').val(totalValue);
            },

            disableNonEditableFields: function () {
                this.$el.find('select[name=code_type]').attr('disabled', true);
                this.$el.find('select[name=voucher_type]').attr('disabled', true);
                this.$el.find('input[name=quantity]').attr('disabled', true);
                this.$el.find('input[name=course_id]').attr('disabled', true);
                this.$el.find('input[name=code]').attr('disabled', true);
                this.$el.find('input[name=benefit_type]').attr('disabled', true);
                this.$el.find('select[name=seat_type]').attr('disabled', true);
                this.$el.find('input[name=max_uses]').attr('disabled', true);
            },

            getSeatData: function () {
                return this.$el.find('[value=' + this.getSeatType() + ']').data();
            },

            getSeatType: function () {
                return this.$el.find('[name=seat_type]').val();
            },

            previewCatalog: function (event) {
                // TODO:
                // Make an AJAX call to the API endpoint that will process dynamic catalog query
                event.preventDefault();

                var courses = ['Course 1', 'Course 2'];
                this.courses = _.map(courses, function (course) {
                    return $('<li></li>')
                        .text(course);
                });


                this.$el.find('#number_of_courses > .value').html('2');
                this.$el.find('#courses > .value > ul').html(this.courses);
            },

            getHelpWithCatalog: function (event) {
                // TODO:
                // Update this function once the requirements are provided
                event.preventDefault();
                alert('Get Help With Catalog');
            },

            render: function () {
                // Render the parent form/template
                this.$el.html(this.template(this.model.attributes));
                this.stickit();

                // Avoid the need to create this jQuery object every time an alert has to be rendered.
                this.$alerts = this.$el.find('.alerts');

                if (this.editing) {
                    this.$el.find('select[name=category]').val(this.model.get('categories')[0].id).trigger('change');
                    this.disableNonEditableFields();
                    this.toggleFields();
                    this.$el.find('button[type=submit]').html(gettext('Save Changes'));
                    this.fillFromCourse();
                } else {
                    var firstEntry = function(obj, i){ return i === 0 ? obj : null; },
                        defaultCategory = ecommerce.coupons.categories.filter(firstEntry);
                    this.model.set('coupon_type', this.codeTypes[0].value);
                    this.model.set('voucher_type', this.voucherTypes[0].value);
                    this.model.set('category', defaultCategory[0].id);
                    this.model.set('benefit_type', 'Percentage');
                    this.$el.find('[name=benefit_value]').attr('max', 100);
                    this.$el.find('button[type=submit]').html(gettext('Create Coupon'));
                }

                // Add date picker
                Utils.addDatePicker(this);

                this._super();
                return this;
            },

            /**
             * Override default saveSuccess.
             */
            saveSuccess: function (model, response) {
                this.goTo(response.coupon_id ? response.coupon_id.toString() : response.id.toString());
            }
        });
    }
);
